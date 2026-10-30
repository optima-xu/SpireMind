import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from spiremind.core.run import RunMemory


class MemoryStore:
    def __init__(self, path: Path, snapshot_limit: int = 2048):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_limit = max(1, snapshot_limit)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS runs (id TEXT, version TEXT, payload TEXT, PRIMARY KEY(id,version));
          CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, payload TEXT);
        """)
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS working_scopes
            (instance TEXT, agent TEXT, task TEXT, payload TEXT, PRIMARY KEY(instance,agent,task));
          CREATE TABLE IF NOT EXISTS memory_audit
            (id INTEGER PRIMARY KEY, instance TEXT, producer TEXT, payload TEXT);
          CREATE TABLE IF NOT EXISTS handoffs
            (id TEXT PRIMARY KEY, instance TEXT, producer TEXT, consumer TEXT, payload TEXT);
          CREATE TABLE IF NOT EXISTS committed_transitions
            (id TEXT PRIMARY KEY, instance TEXT, payload TEXT);
          PRAGMA user_version=4;
        """)
        self.transactions = 0
        self.queries = 0
        self._scope_payloads = {}
        self._persisted_payloads: dict[tuple[str, str], str] = {}
        self._snapshot_ids = {row[0] for row in self.db.execute("SELECT id FROM snapshots")}

    def load(self, run_id: str, version: str) -> RunMemory | None:
        row = self.db.execute(
            "SELECT payload FROM runs WHERE id=? AND version=?", (run_id, version)
        ).fetchone()
        if row:
            self._persisted_payloads[(run_id, version)] = row[0]
            return RunMemory.model_validate_json(row[0])
        return None

    def persist(self, memory: RunMemory) -> None:
        self.save_context(memory, None)

    def save_context(
        self,
        memory: RunMemory,
        value: Any,
        *,
        scopes=None,
        audit=None,
        handoff=None,
        evidence=None,
        transition_id=None,
        expected_policy_version=None,
    ) -> str:
        """Publish caches only after commit; run, context and evidence share one transaction."""
        run_payload = memory.model_dump_json()
        key = (memory.run_id, memory.game_version)
        payload = self._snapshot_payload(value) if value is not None else None
        snapshot = hashlib.sha256(payload.encode()).hexdigest()[:20] if payload is not None else ""
        scope_changes = {
            (agent, task): working.model_dump_json()
            for (agent, task), working in (scopes or {}).items()
            if self._scope_payloads.get((memory.instance_id, agent, task)) != working.model_dump_json()
        }
        changed = self._persisted_payloads.get(key) != run_payload
        new_snapshot = payload is not None and snapshot not in self._snapshot_ids
        removed_scopes = set(self.scopes(memory.instance_id)) - set(scopes) if scopes is not None else set()
        if not (changed or new_snapshot or scope_changes or removed_scopes or audit or handoff or evidence):
            return snapshot
        with self.db:
            if not self.db.in_transaction:
                self.db.execute("BEGIN IMMEDIATE")
            if expected_policy_version is not None and self.policy_version(memory) != expected_policy_version:
                raise ValueError("Run policy changed before the transition could commit")
            if transition_id:
                self.db.execute(
                    "INSERT INTO committed_transitions VALUES (?,?,?)",
                    (transition_id, memory.instance_id, self._snapshot_payload(audit)),
                )
            if changed:
                self.db.execute(
                    "INSERT INTO runs VALUES (?,?,?) ON CONFLICT(id,version) "
                    "DO UPDATE SET payload=excluded.payload",
                    (*key, run_payload),
                )
            if new_snapshot:
                self.db.execute("INSERT OR IGNORE INTO snapshots VALUES (?,?)", (snapshot, payload))
                self.db.execute(
                    "DELETE FROM snapshots WHERE rowid NOT IN "
                    "(SELECT rowid FROM snapshots ORDER BY rowid DESC LIMIT ?)",
                    (self.snapshot_limit,),
                )
            for (agent, task), scope_payload in scope_changes.items():
                self.db.execute(
                    "INSERT OR REPLACE INTO working_scopes VALUES (?,?,?,?)",
                    (memory.instance_id, agent, task, scope_payload),
                )
            for agent, task in removed_scopes:
                self.db.execute(
                    "DELETE FROM working_scopes WHERE instance=? AND agent=? AND task=?",
                    (memory.instance_id, agent, task),
                )
            if audit:
                self.db.execute(
                    "INSERT INTO memory_audit(instance,producer,payload) VALUES (?,?,?)",
                    (memory.instance_id, audit["producer"], self._snapshot_payload(audit)),
                )
            if evidence:
                evidence()
            if handoff:
                self.db.execute(
                    "INSERT OR REPLACE INTO handoffs VALUES (?,?,?,?,?)",
                    (
                        handoff["id"],
                        memory.instance_id,
                        handoff["producer"],
                        handoff["consumer"],
                        self._snapshot_payload(handoff),
                    ),
                )
        self.transactions += 1
        for agent, task in removed_scopes:
            self._scope_payloads.pop((memory.instance_id, agent, task), None)
        self._scope_payloads.update(
            {(memory.instance_id, agent, task): payload for (agent, task), payload in scope_changes.items()}
        )
        self._persisted_payloads[key] = run_payload
        if new_snapshot:
            self._snapshot_ids = {row[0] for row in self.db.execute("SELECT id FROM snapshots")}
        return snapshot

    def committed_transition(self, identity):
        row = self.db.execute("SELECT payload FROM committed_transitions WHERE id=?", (identity,)).fetchone()
        return json.loads(row[0]) if row else None

    def scopes(self, instance):
        from spiremind.core.working import WorkingMemory

        return {
            (agent, task): WorkingMemory.model_validate_json(payload)
            for agent, task, payload in self.db.execute(
                "SELECT agent,task,payload FROM working_scopes WHERE instance=?", (instance,)
            )
        }

    def policy_version(self, memory):
        row = self.db.execute(
            "SELECT payload FROM runs WHERE id=? AND version=?", (memory.run_id, memory.game_version)
        ).fetchone()
        return json.loads(row[0]).get("policy_version", 0) if row else memory.policy_version

    @staticmethod
    def _snapshot_payload(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def snapshot(self, value: Any) -> str:
        """Backward-compatible standalone snapshot, with rollback-safe bookkeeping."""
        payload = self._snapshot_payload(value)
        snapshot = hashlib.sha256(payload.encode()).hexdigest()[:20]
        if snapshot not in self._snapshot_ids:
            with self.db:
                self.db.execute("INSERT OR IGNORE INTO snapshots VALUES (?,?)", (snapshot, payload))
                self.db.execute(
                    "DELETE FROM snapshots WHERE rowid NOT IN "
                    "(SELECT rowid FROM snapshots ORDER BY rowid DESC LIMIT ?)",
                    (self.snapshot_limit,),
                )
            self.transactions += 1
            self._snapshot_ids = {row[0] for row in self.db.execute("SELECT id FROM snapshots")}
        return snapshot

    def save(self, memory: RunMemory) -> str:
        return self.save_context(memory, {"schema_version": 1, "run": memory.model_dump(mode="json")})

    def load_snapshot(self, snapshot_id: str) -> dict | None:
        row = self.db.execute("SELECT payload FROM snapshots WHERE id=?", (snapshot_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def close(self):
        self.db.close()
