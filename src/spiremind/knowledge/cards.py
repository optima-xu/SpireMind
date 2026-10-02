import hashlib
import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from spiremind.core.cache import LRU
from spiremind.core.state import PublicFacts


class CardFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    card_id: str
    game_version: str
    source_version: str
    text: str
    upgraded: bool = False
    cost: int | None = None
    star_cost: int | None = None
    type: str = ""
    values: PublicFacts = Field(default_factory=PublicFacts)

    def context_view(self):
        return self.model_dump(exclude={"values"}) | {"values": self.values.unpack()}


class CardDB:
    """Exact-version static facts only. Runtime hand values always take precedence."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS cards (version TEXT, id TEXT, upgraded INTEGER, "
            "payload TEXT, PRIMARY KEY(version,id,upgraded))"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS card_sets (version TEXT PRIMARY KEY, source_version TEXT, "
            "content_sha256 TEXT, card_count INTEGER)"
        )
        self.cache = LRU(1024)
        self.generation = 0
        self.lookup_queries = 0

    def _invalidate(self):
        self.generation += 1
        self.cache.clear()

    def put(self, fact: CardFact):
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO cards VALUES (?,?,?,?)",
                (fact.game_version, fact.card_id, fact.upgraded, fact.model_dump_json()),
            )
            self._refresh_metadata(fact.game_version)
        self._invalidate()

    @staticmethod
    def _digest(facts: Iterable[CardFact]) -> str:
        rows = sorted(
            (fact.model_dump(mode="json") for fact in facts),
            key=lambda row: (row["card_id"], row["upgraded"]),
        )
        payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def _refresh_metadata(self, version: str) -> None:
        facts = [
            CardFact.model_validate_json(row[0])
            for row in self.db.execute("SELECT payload FROM cards WHERE version=?", (version,))
        ]
        sources = ",".join(sorted({fact.source_version for fact in facts}))
        self.db.execute(
            "INSERT OR REPLACE INTO card_sets VALUES (?,?,?,?)",
            (version, sources, self._digest(facts), len(facts)),
        )

    def put_many(self, facts: Iterable[CardFact]) -> int:
        """Replace each supplied version atomically and remove stale rows."""
        groups: dict[str, list[CardFact]] = defaultdict(list)
        for fact in facts:
            groups[fact.game_version].append(fact)
        with self.db:
            for version, version_facts in groups.items():
                self.db.execute("DELETE FROM cards WHERE version=?", (version,))
                self.db.executemany(
                    "INSERT INTO cards VALUES (?,?,?,?)",
                    [
                        (fact.game_version, fact.card_id, fact.upgraded, fact.model_dump_json())
                        for fact in version_facts
                    ],
                )
                sources = ",".join(sorted({fact.source_version for fact in version_facts}))
                self.db.execute(
                    "INSERT OR REPLACE INTO card_sets VALUES (?,?,?,?)",
                    (version, sources, self._digest(version_facts), len(version_facts)),
                )
        self._invalidate()
        return sum(len(group) for group in groups.values())

    def lookup(self, ids: set[str] | set[tuple[str, bool]], version: str) -> list[CardFact]:
        """Fetch base/upgraded identities in one query.

        A bare id means the base card for backward compatibility. Callers that
        know runtime upgrade state should pass ``(id, upgraded)`` pairs.
        """
        requested = {(item if isinstance(item, tuple) else (item, False)) for item in ids}
        missing, result = set(), []
        for card_id, upgraded in sorted(requested):
            found, fact = self.cache.get((self.generation, version, card_id, upgraded))
            if not found:
                missing.add((card_id, upgraded))
            elif fact is not None:
                result.append(fact)
        # Negative entries are cached too; an unknown card must not cause a query per turn.
        if missing:
            names = sorted({identity[0] for identity in missing})
            placeholders = ",".join("?" for _ in names)
            self.lookup_queries += 1
            rows = self.db.execute(
                f"SELECT id,upgraded,payload FROM cards WHERE version=? AND id IN ({placeholders})",
                (version, *names),
            )
            fetched = {
                (name, bool(upgraded)): CardFact.model_validate_json(payload)
                for name, upgraded, payload in rows
            }
            for card_id, upgraded in sorted(missing):
                fact = fetched.get((card_id, upgraded))
                self.cache.put((self.generation, version, card_id, upgraded), fact)
                if fact is not None:
                    result.append(fact)
        return sorted(result, key=lambda fact: (fact.card_id, fact.upgraded))

    def count(self, version: str) -> int:
        return self.db.execute("SELECT COUNT(*) FROM cards WHERE version=?", (version,)).fetchone()[0]

    def metadata(self, version: str) -> dict | None:
        row = self.db.execute(
            "SELECT source_version,content_sha256,card_count FROM card_sets WHERE version=?", (version,)
        ).fetchone()
        return {"source_version": row[0], "content_sha256": row[1], "card_count": row[2]} if row else None

    def needs_sync(
        self,
        version: str,
        *,
        expected_source_version: str | None = None,
        expected_digest: str | None = None,
        facts: Iterable[CardFact] | None = None,
    ) -> bool:
        rows = self.db.execute("SELECT payload FROM cards WHERE version=?", (version,)).fetchall()
        if not rows:
            return True
        if any(
            "values" not in (fact := json.loads(row[0]))
            and fact.get("source_version", "").startswith("loaded_game_model:")
            for row in rows
        ):
            return True
        metadata = self.metadata(version)
        if metadata is None or metadata["card_count"] != len(rows):
            return True
        if expected_source_version is not None and metadata["source_version"] != expected_source_version:
            return True
        if facts is not None:
            expected_digest = self._digest(fact for fact in facts if fact.game_version == version)
        return expected_digest is not None and metadata["content_sha256"] != expected_digest

    def import_json(self, path: Path) -> int:
        facts = [CardFact.model_validate(x) for x in json.loads(path.read_text(encoding="utf-8"))]
        return self.put_many(facts)

    def close(self):
        self.db.close()
