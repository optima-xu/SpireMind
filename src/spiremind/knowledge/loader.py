"""Version-checked loaders for STS2 enemy catalog, character strategy packages, and card DB."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from threading import RLock

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from spiremind.domain.safety import LRU
from spiremind.domain.state import CardFact, Enemy, GameState

# --- from knowledge/library.py ---


def version_matches(pattern: str, version: str) -> bool:
    pattern, version = pattern.removeprefix("v"), version.removeprefix("v")
    return version.startswith(pattern[:-1]) if pattern.endswith("x") else pattern == version


class StrategyPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    character: str
    game_version: str
    source: str
    archetype: str
    strong_signals: tuple[str, ...]
    enablers: tuple[str, ...]
    payoffs: tuple[str, ...]
    goals: tuple[str, ...]
    hard_rules: tuple[str, ...]
    heuristics: tuple[str, ...]
    anti_patterns: tuple[str, ...]
    scenes: tuple[str, ...] = ("combat", "run", "map")


class StrategyLibrary:
    def __init__(self, root: Path | None = None):
        root = root or Path(__file__).parent / "strategies"
        self.packages = tuple(
            StrategyPackage.model_validate(p)
            for path in sorted(root.glob("*/*.yaml"))
            for p in yaml.safe_load(path.read_text(encoding="utf-8"))
        )
        self.knowledge_version = hashlib.sha256(
            "".join(p.model_dump_json() for p in self.packages).encode()
        ).hexdigest()
        self.cache = LRU(128)
        self._cache_lock = RLock()

    def scores(self, state: GameState) -> list[tuple[float, StrategyPackage]]:
        """Return persistent deck fit scores.

        The score deliberately excludes the current hand. A shuffled draw must not
        make the long-lived run memory oscillate between archetypes.
        """
        key = (
            self.knowledge_version,
            state.game_version,
            state.run.character,
            tuple((c.id, c.count) for c in state.run.deck),
            tuple(r.id for r in state.run.relics),
        )
        with self._cache_lock:
            found, scores = self.cache.get(key)
        if found:
            return list(scores)
        result = self._scores(state)
        with self._cache_lock:
            self.cache.put(key, tuple(result))
        return result

    def _scores(self, state):
        deck = [card.id for card in state.run.deck for _ in range(card.count)]
        present = set(deck) | {r.id for r in state.run.relics}
        result = []
        for p in self.packages:
            if p.character != state.run.character or not version_matches(p.game_version, state.game_version):
                continue
            core = len(present & set(p.strong_signals)) / max(1, len(p.strong_signals))
            enabler = min(1, sum(c in p.enablers for c in deck) / max(1, len(deck) * 0.15))
            payoff = min(1, sum(c in p.payoffs for c in deck) / max(1, len(deck) * 0.1))
            fit = min(enabler, payoff)
            penalty = 0.15 if enabler and not payoff else 0
            score = max(0, 0.35 * core + 0.25 * enabler + 0.25 * payoff + 0.15 * fit - penalty)
            result.append((round(score, 3), p))
        return sorted(result, key=lambda pair: (-pair[0], pair[1].id))

    @staticmethod
    def _scene_relevance(state: GameState, package: StrategyPackage) -> float:
        """Score only the cards visible at this decision, separately from deck fit."""
        if state.combat:
            visible = {card.id for card in state.combat.hand}
        else:
            visible = {choice.card.id for choice in state.choices if choice.card}
            visible.update(action.card_id for action in state.legal_actions if action.card_id)
        if visible & set(package.strong_signals):
            return 1.0
        if visible & set(package.payoffs):
            return 0.75
        if visible & set(package.enablers):
            return 0.5
        return 0.0

    def retrieve_detailed(
        self, state: GameState, agent: str, k: int = 3, minimum: float = 0.35
    ) -> list[tuple[float, float, StrategyPackage]]:
        """Return ``(deck_fit, scene_relevance, package)`` without conflating the two."""
        candidates = []
        for deck_fit, package in self.scores(state):
            if agent not in package.scenes:
                continue
            scene_relevance = self._scene_relevance(state, package)
            # A visible offered/held signal makes anti-patterns and hard rules
            # useful even before the deck has committed to the archetype.
            if deck_fit >= minimum or scene_relevance > 0:
                rank = deck_fit + 0.2 * scene_relevance
                candidates.append((rank, deck_fit, scene_relevance, package))
        candidates.sort(key=lambda row: (-row[0], row[3].id))
        return [
            (deck_fit, scene_relevance, package) for _, deck_fit, scene_relevance, package in candidates[:k]
        ]

    def retrieve(self, state: GameState, agent: str, k: int = 3, minimum: float = 0.35):
        return [
            (round(deck_fit + 0.2 * scene_relevance, 3), package)
            for deck_fit, scene_relevance, package in self.retrieve_detailed(state, agent, k, minimum)
        ]


# --- from knowledge/enemies.py ---


class EnemyMoveFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    name_zh: str = ""
    intent: str
    damage: dict[str, int | None] | None = None
    block: int | None = None
    heal: int | None = None
    powers: tuple[dict[str, str | int], ...] = ()


class EnemyFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    source_id: str
    name: str
    name_zh: str = ""
    type: str
    acts: tuple[str, ...] = ()
    hp: dict[str, int | None]
    moves: tuple[EnemyMoveFact, ...]
    pattern: dict[str, str] = Field(default_factory=dict)
    innate_powers: tuple[dict[str, str | int | None], ...] = ()
    traits: tuple[str, ...]
    strategy: tuple[str, ...]

    def context_view(self) -> dict:
        """Return only concise planning guidance, never the full local bestiary row."""
        traits = [trait for trait in self.traits if not trait.startswith("Encounter:")][:3]
        return {
            "id": self.id,
            "name": self.name,
            "name_zh": self.name_zh,
            "type": self.type,
            "traits": traits,
            "strategy": list(self.strategy[:2]),
        }


class EnemyCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int
    game_version: str
    source_version: str
    enemy_count: int
    source: dict
    enemies: tuple[EnemyFact, ...]

    @model_validator(mode="after")
    def validate_catalog(self):
        ids = [enemy.id for enemy in self.enemies]
        if self.enemy_count != len(self.enemies):
            raise ValueError("enemy_count does not match enemies")
        if len(ids) != len(set(ids)):
            raise ValueError("enemy ids must be unique")
        return self


class EnemyKnowledge:
    """Version-pinned local enemy facts selected by exact normalized bridge id."""

    DEFAULT_FILE = Path(__file__).parent / "enemies" / "v0.111.0.json"

    def __init__(self, path: Path | None = None):
        self.path = path or self.DEFAULT_FILE
        self.catalog = EnemyCatalog.model_validate_json(self.path.read_text(encoding="utf-8"))
        self._by_id = {enemy.id: enemy for enemy in self.catalog.enemies}

    def lookup(self, enemies: tuple[Enemy, ...], game_version: str) -> list[EnemyFact]:
        if not version_matches(self.catalog.game_version, game_version):
            return []
        result = []
        seen = set()
        for enemy in enemies:
            if not enemy.alive or enemy.id in seen:
                continue
            seen.add(enemy.id)
            fact = self._by_id.get(enemy.id)
            if fact:
                result.append(fact)
        return result

    def context_for(self, enemies: tuple[Enemy, ...], game_version: str) -> list[dict]:
        return [fact.context_view() for fact in self.lookup(enemies, game_version)]

    def get(self, enemy_id: str) -> EnemyFact | None:
        return self._by_id.get(enemy_id)

    def metadata(self) -> dict:
        return {
            "schema_version": self.catalog.schema_version,
            "game_version": self.catalog.game_version,
            "source_version": self.catalog.source_version,
            "enemy_count": self.catalog.enemy_count,
            "content_sha256": self.catalog.source.get("content_sha256", ""),
        }


# --- from adapters/storage/cards.py ---


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
