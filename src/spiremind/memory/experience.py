"""Evidence-backed episodic retrieval and conditional, versioned learned skills.

Execution success establishes a transition, never a claim that a policy is optimal.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from spiremind.context.budget import estimate_tokens
from spiremind.core.cache import LRU
from spiremind.core.state import GameState


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def symbols(state: GameState) -> list[str]:
    cards = list(state.run.deck) + (list(state.combat.hand) if state.combat else [])
    cards += [choice.card for choice in state.choices if choice.card]
    return sorted(
        {c.id for c in cards}
        | {r.id for r in state.run.relics}
        | ({e.id for e in state.combat.enemies if e.alive} if state.combat else set())
    )


class LessonProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner: Literal["combat", "run", "map", "event"]
    game_version: str
    character: str
    scene: str
    conditions: dict
    metric: Literal["hp_delta", "block_delta", "deck_delta", "gold_delta"]
    value: int
    evidence_ids: list[str] = Field(min_length=1, max_length=30)
    instruction: str = Field(min_length=1, max_length=300)


class ExperienceStore:
    def __init__(self, db):
        self.db = db
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS episodes
            (id TEXT PRIMARY KEY, lineage TEXT, partition_name TEXT, version TEXT, character TEXT,
             agent TEXT, scene TEXT, signature TEXT, verified INTEGER, payload TEXT);
          CREATE INDEX IF NOT EXISTS episode_scope
            ON episodes(partition_name,version,character,agent,scene,verified);
          CREATE VIRTUAL TABLE IF NOT EXISTS episode_fts USING fts5(id UNINDEXED, terms);
          CREATE TABLE IF NOT EXISTS lessons
            (id TEXT PRIMARY KEY, revision INTEGER, status TEXT, payload TEXT);
          CREATE TABLE IF NOT EXISTS lesson_history
            (id TEXT, revision INTEGER, status TEXT, payload TEXT, PRIMARY KEY(id,revision));
          CREATE TABLE IF NOT EXISTS reflection_jobs
            (id TEXT PRIMARY KEY, status TEXT, attempts INTEGER DEFAULT 0, payload TEXT);
          CREATE TABLE IF NOT EXISTS memory_meta (key TEXT PRIMARY KEY, payload TEXT);
          CREATE TABLE IF NOT EXISTS import_sources
            (id TEXT PRIMARY KEY, payload TEXT);
        """)
        self.cache = LRU(256)
        self.generation = 0

    def changed(self):
        self.generation += 1
        self.cache.clear()

    @staticmethod
    def episode(old, action, new, producer, consumer, verified, lineage, handoff=None):
        card = next(
            (c for c in (old.combat.hand if old.combat else ()) if action.card_id in {c.id, c.ref}), None
        )
        conditions = dict(
            kind=action.kind.value, card=card.id if card else "", upgraded=bool(card and card.upgraded)
        )
        if old.combat:
            conditions["powers"] = sorted([p.id, p.amount] for p in old.combat.powers)
        metrics = {
            "hp_delta": new.run.hp - old.run.hp,
            "gold_delta": new.run.gold - old.run.gold,
            "deck_delta": sum(c.count for c in new.run.deck) - sum(c.count for c in old.run.deck),
        }
        if (
            old.combat
            and new.combat
            and old.combat.turn == new.combat.turn
            and old.run.floor == new.run.floor
        ):
            metrics["block_delta"] = new.combat.block - old.combat.block
        if old.combat and (not new.combat or old.combat.turn != new.combat.turn):
            metrics.pop("hp_delta", None)
        # Do not turn a terminal/reset transition into a fictional card effect.
        if old.run.id != new.run.id or old.run.floor != new.run.floor or new.terminal:
            metrics = {}
        evidence = dict(
            before=old.model_dump(mode="json"),
            after=new.model_dump(mode="json"),
            kind=action.kind.value,
            conditions=conditions,
            observations=metrics,
            producer=producer,
            consumer=consumer,
            verified=verified,
            handoff_id=handoff["id"] if handoff else None,
            upstream_policy_version=handoff.get("upstream_policy_version") if handoff else None,
            lineage=lineage,
            terms=symbols(old),
        )
        evidence["id"] = digest(
            [lineage, old.decision_id, old.revision, action.id, new.decision_id, new.revision]
        )
        evidence["signature"] = digest(
            [old.game_version, old.run.character, producer, old.scene.value, conditions]
        )
        return evidence

    def insert(self, episode, partition="train", *, commit=True):
        old = episode["before"]
        cursor = self.db.execute(
            "INSERT OR IGNORE INTO episodes VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                episode["id"],
                episode["lineage"],
                partition,
                old["game_version"],
                old["run"]["character"],
                episode["producer"],
                old["scene"],
                episode["signature"],
                int(episode["verified"]),
                json.dumps(episode, ensure_ascii=False),
            ),
        )
        if cursor.rowcount:
            self.db.execute(
                "INSERT INTO episode_fts VALUES (?,?)", (episode["id"], " ".join(episode["terms"]))
            )
        if commit:
            self.db.commit()
            self.changed()
        return bool(cursor.rowcount)

    def observe(self, old, action, new, producer, consumer, verified, lineage, handoff):
        episode = self.episode(old, action, new, producer, consumer, verified, lineage, handoff)
        self.insert(episode)
        if new.terminal or (old.combat and not new.combat) or not verified:
            self.enqueue(
                lineage, reason="terminal" if new.terminal else "combat_end" if verified else "error"
            )
        self.check_contradictions(episode)

    def enqueue(self, lineage, reason="manual", *, commit=True):
        evidence = [
            row[0]
            for row in self.db.execute(
                "SELECT id FROM episodes WHERE lineage=? AND partition_name='train' AND verified=1 "
                "ORDER BY rowid DESC LIMIT 30",
                (lineage,),
            )
        ]
        if not evidence:
            return
        payload = dict(lineage=lineage, reason=reason, evidence_ids=evidence)
        self.db.execute(
            "INSERT OR IGNORE INTO reflection_jobs(id,status,payload) VALUES (?,'pending',?)",
            (digest(payload), json.dumps(payload)),
        )
        if commit:
            self.db.commit()

    def compact(self, evidence_id):
        row = self.db.execute(
            "SELECT payload,partition_name FROM episodes WHERE id=?", (evidence_id,)
        ).fetchone()
        if not row:
            raise ValueError("unknown_evidence_id")
        evidence = json.loads(row[0])
        return dict(
            id=evidence_id,
            partition=row[1],
            lineage=evidence["lineage"],
            owner=evidence["producer"],
            game_version=evidence["before"]["game_version"],
            character=evidence["before"]["run"]["character"],
            scene=evidence["before"]["scene"],
            conditions=evidence["conditions"],
            observations=evidence["observations"],
            verified=evidence["verified"],
        )

    def propose(self, proposal: LessonProposal):
        evidence = [self.compact(key) for key in proposal.evidence_ids]
        expected = (proposal.owner, proposal.game_version, proposal.character, proposal.scene)
        if proposal.conditions.get("kind") not in {"play_card", "choose_card", "buy_item", "rest"}:
            raise ValueError("unsupported_effect_attribution")
        if any(
            not e["verified"]
            or e["partition"] != "train"
            or (e["owner"], e["game_version"], e["character"], e["scene"]) != expected
            or e["conditions"] != proposal.conditions
            or e["observations"].get(proposal.metric) != proposal.value
            for e in evidence
        ):
            raise ValueError("lesson_not_supported_by_cited_evidence")
        identity = digest([expected, proposal.conditions, proposal.metric])
        previous = self.db.execute("SELECT revision FROM lessons WHERE id=?", (identity,)).fetchone()
        revision = previous[0] + 1 if previous else 1
        status = "active" if len({e["lineage"] for e in evidence}) >= 3 else "candidate"
        # Deterministic regression also checks uncited observations of the exact same conditions.
        for row in self.db.execute(
            "SELECT payload FROM episodes WHERE partition_name='train' AND verified=1 AND version=? "
            "AND character=? AND agent=? AND scene=?",
            (proposal.game_version, proposal.character, proposal.owner, proposal.scene),
        ):
            other = json.loads(row[0])
            if other["conditions"] == proposal.conditions and proposal.metric in other["observations"]:
                if other["observations"][proposal.metric] != proposal.value:
                    status = "disabled"
        # Only a canonical evidence summary is eligible for injection; model prose stays untrusted.
        proposal.instruction = (
            f"Repeated verified observation: {proposal.conditions.get('card', '')} "
            f"{proposal.conditions.get('kind', '')}, {proposal.metric}={proposal.value}. "
            "Check current text/powers. This is conditional evidence, not an optimality claim."
        )
        payload = proposal.model_dump_json()
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO lessons VALUES (?,?,?,?)", (identity, revision, status, payload)
            )
            self.db.execute(
                "INSERT INTO lesson_history VALUES (?,?,?,?)", (identity, revision, status, payload)
            )
        self.changed()
        return dict(id=identity, revision=revision, status=status)

    def check_contradictions(self, episode):
        if not episode["verified"]:
            return
        for identity, revision, payload in self.db.execute(
            "SELECT id,revision,payload FROM lessons WHERE status='active'"
        ).fetchall():
            p = LessonProposal.model_validate_json(payload)
            if (
                episode["producer"] == p.owner
                and episode["before"]["game_version"] == p.game_version
                and episode["before"]["run"]["character"] == p.character
                and episode["before"]["scene"] == p.scene
                and episode["conditions"] == p.conditions
                and p.metric in episode["observations"]
                and episode["observations"][p.metric] != p.value
            ):
                with self.db:
                    self.db.execute(
                        "UPDATE lessons SET revision=?,status='disabled' WHERE id=?", (revision + 1, identity)
                    )
                    self.db.execute(
                        "INSERT INTO lesson_history VALUES (?,?,'disabled',?)",
                        (identity, revision + 1, payload),
                    )
                self.changed()

    def consolidate(self):
        """Offline reflection derives observations, never unsupported strategic superiority."""
        grouped = {}
        for row in self.db.execute(
            "SELECT payload FROM episodes WHERE partition_name='train' AND verified=1"
        ):
            episode = json.loads(row[0])
            for metric, value in episode["observations"].items():
                if (
                    value
                    and metric in {"block_delta", "hp_delta", "deck_delta"}
                    and episode["kind"] in {"play_card", "choose_card", "buy_item", "rest"}
                ):
                    grouped.setdefault((episode["signature"], metric, value), []).append(episode)
        results = []
        for (_, metric, value), episodes in grouped.items():
            if len({e["lineage"] for e in episodes}) < 3:
                continue
            first = episodes[0]
            conditions = first["conditions"]
            instruction = (
                f"Verified repeated observation for {conditions['kind']} {conditions['card']}: "
                f"{metric}={value}. Compare current text and powers. "
                "This does not establish an optimal choice."
            )
            results.append(
                self.propose(
                    LessonProposal(
                        owner=first["producer"],
                        game_version=first["before"]["game_version"],
                        character=first["before"]["run"]["character"],
                        scene=first["before"]["scene"],
                        conditions=conditions,
                        metric=metric,
                        value=value,
                        evidence_ids=list(
                            dict.fromkeys(
                                [
                                    next(e["id"] for e in episodes if e["lineage"] == lineage)
                                    for lineage in sorted({e["lineage"] for e in episodes})
                                ]
                                + [e["id"] for e in episodes]
                            )
                        )[:30],
                        instruction=instruction,
                    )
                )
            )
        self.db.execute("UPDATE reflection_jobs SET status='complete' WHERE status='pending'")
        self.db.commit()
        return results

    def retrieve(self, state, agent):
        terms = symbols(state)
        powers = sorted([p.id, p.amount] for p in state.combat.powers) if state.combat else []
        key = (
            self.generation,
            state.game_version,
            state.run.character,
            agent,
            state.scene.value,
            tuple(terms),
            repr(powers),
            tuple((c.id, c.upgraded) for c in state.combat.hand) if state.combat else (),
        )
        found, result = self.cache.get(key)
        if found:
            return json.loads(json.dumps(result))
        scope = (state.game_version, state.run.character, agent, state.scene.value)
        # Symbolic terms are quoted and bound; model text is never an SQL/FTS expression.
        expression = " OR ".join('"' + word + '"' for word in terms if re.fullmatch(r"[\w-]{1,80}", word))
        rows = []
        if expression:
            rows = self.db.execute(
                "SELECT e.payload FROM episode_fts f JOIN episodes e ON e.id=f.id "
                "WHERE episode_fts MATCH ? AND e.partition_name='train' AND e.verified=1 "
                "AND e.version=? AND e.character=? AND e.agent=? AND e.scene=? "
                "ORDER BY bm25(episode_fts),e.id LIMIT 2",
                (expression, *scope),
            ).fetchall()
        examples = []
        for row in rows:
            e = json.loads(row[0])
            examples.append(
                dict(
                    evidence_id=e["id"],
                    conditions=e["conditions"],
                    observations=e["observations"],
                    status="verified_transition_not_optimality",
                )
            )
        skills = []
        for identity, payload in self.db.execute(
            "SELECT id,payload FROM lessons WHERE status='active' ORDER BY id"
        ):
            p = LessonProposal.model_validate_json(payload)
            if (p.game_version, p.character, p.owner, p.scene) != scope:
                continue
            if p.conditions.get("card"):
                visible_cards = (
                    state.combat.hand
                    if state.combat
                    else tuple(choice.card for choice in state.choices if choice.card)
                )
                if not any(
                    c.id == p.conditions["card"] and c.upgraded == p.conditions.get("upgraded", False)
                    for c in visible_cards
                ):
                    continue
            if p.conditions.get("powers", []) != powers:
                continue
            skills.append(
                dict(
                    id=identity,
                    instruction=p.instruction,
                    conditions=p.conditions,
                    evidence_ids=p.evidence_ids[:3],
                )
            )
            if len(skills) == 3:
                break
        result = dict(episodes=examples, skills=skills)
        while estimate_tokens(result) > 600:
            (result["episodes"] or result["skills"]).pop()
        self.cache.put(key, result)
        return json.loads(json.dumps(result))

    def inspect(self):
        return {
            table: dict(self.db.execute(f"SELECT {column},COUNT(*) FROM {table} GROUP BY {column}"))
            for table, column in [
                ("episodes", "partition_name"),
                ("lessons", "status"),
                ("reflection_jobs", "status"),
            ]
        }


def import_history(store: ExperienceStore, root: Path):
    """Split whole seed lineages chronologically before learning; repeated attempts stay together."""
    from spiremind.core.actions import Action
    from spiremind.memory.manager import MemoryManager

    traces = []
    malformed = unjoined = inserted = 0
    for path in sorted(root.glob("*/summary.json")):
        summary = json.loads(path.read_text(encoding="utf-8"))
        if summary.get("mode") != "live":
            continue
        states_path, decisions_path = path.parent / "states.jsonl", path.parent / "decisions.jsonl"
        if not states_path.exists() or not decisions_path.exists():
            continue
        states = {}
        for line in states_path.read_text(encoding="utf-8").splitlines():
            try:
                state = GameState.model_validate_json(line)
                states[(state.decision_id, state.revision)] = state
            except ValueError:
                malformed += 1
        records = []
        for line in decisions_path.read_text(encoding="utf-8").splitlines():
            try:
                records.append(json.loads(line))
            except ValueError:
                malformed += 1
        keys = sorted(
            {
                (s.game_version, s.run.character, s.run.id)
                for s in states.values()
                if s.run.id not in {"menu", "run_unknown", ""}
                and s.run.character != "unknown"
                and s.scene.value not in {"game_over", "main_menu", "character_select"}
            }
        )
        traces.append((path.parent.name, keys, states, records))
    lineages = list(dict.fromkeys(key for _, keys, _, _ in traces for key in keys))
    split = max(1, int(len(lineages) * 0.7))
    train = {digest(key) for key in lineages[:split]}
    previous = store.db.execute("SELECT payload FROM memory_meta WHERE key='history_split'").fetchone()
    if previous:
        train = set(json.loads(previous[0])["train"])
    else:
        store.db.execute(
            "INSERT INTO memory_meta VALUES ('history_split',?)",
            (json.dumps({"train": sorted(train), "holdout": [digest(k) for k in lineages[split:]]}),),
        )
        store.db.commit()
    for _attempt, _keys, states, records in traces:
        by_decision = {state.decision_id: state for state in states.values()}
        for index, row in enumerate(records):
            old = states.get((row.get("decision_id"), row.get("state_revision")))
            receipt = row.get("execution_result") or {}
            new = by_decision.get(receipt.get("next_decision_id"))
            if new is None and index + 1 < len(records):
                new = states.get(
                    (records[index + 1].get("decision_id"), records[index + 1].get("state_revision"))
                )
            if old is None or new is None or not row.get("action"):
                unjoined += 1
                continue
            lineage_key = (old.game_version, old.run.character, old.run.id)
            if lineage_key not in lineages:
                continue
            try:
                action = Action.model_validate(row["action"])
                producer = row.get("strategy_name") or MemoryManager.owner(old)
                if producer not in {"combat", "run", "map", "event"}:
                    continue
                verified = (
                    row.get("semantic_success") is True
                    and row.get("verify_ok") is True
                    and receipt.get("status") == "completed"
                    and receipt.get("action_id") == action.id
                    and receipt.get("previous_decision_id") == old.decision_id
                    and receipt.get("next_decision_id") == new.decision_id
                )
                episode = store.episode(
                    old, action, new, producer, MemoryManager.owner(new), verified, digest(lineage_key)
                )
                inserted += store.insert(
                    episode, "train" if digest(lineage_key) in train else "holdout", commit=False
                )
            except ValueError:
                malformed += 1
        store.db.commit()
    store.changed()
    report = dict(
        traces=len(traces),
        lineages=len(lineages),
        train_lineages=len(train),
        holdout_lineages=len(lineages) - len(train),
        inserted=inserted,
        malformed=malformed,
        unjoined=unjoined,
        dataset_sha256=digest([(name, records) for name, _, _, records in traces]),
        train_lineage_ids=sorted(train),
        holdout_lineage_ids=[digest(key) for key in lineages if digest(key) not in train],
    )
    store.db.execute(
        "INSERT OR REPLACE INTO import_sources VALUES (?,?)", (report["dataset_sha256"], json.dumps(report))
    )
    store.db.commit()
    return report
