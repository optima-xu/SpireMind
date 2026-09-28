import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .run import RunMemory


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
        payload = memory.model_dump_json()
        key = (memory.run_id, memory.game_version)
        if self._persisted_payloads.get(key) == payload:
            return
        with self.db:
            self.db.execute(
                "INSERT INTO runs VALUES (?,?,?) ON CONFLICT(id,version) "
                "DO UPDATE SET payload=excluded.payload "
                "WHERE runs.payload<>excluded.payload",
                (memory.run_id, memory.game_version, payload),
            )
        self._persisted_payloads[key] = payload

    @staticmethod
    def _snapshot_payload(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def snapshot(self, value: Any) -> str:
        """Store a semantic context snapshot, deduplicated and bounded."""
        payload = self._snapshot_payload(value)
        snapshot = hashlib.sha256(payload.encode()).hexdigest()[:20]
        if snapshot in self._snapshot_ids:
            return snapshot
        with self.db:
            cursor = self.db.execute("INSERT OR IGNORE INTO snapshots VALUES (?,?)", (snapshot, payload))
            if cursor.rowcount:
                self._snapshot_ids.add(snapshot)
                self.db.execute(
                    "DELETE FROM snapshots WHERE rowid NOT IN "
                    "(SELECT rowid FROM snapshots ORDER BY rowid DESC LIMIT ?)",
                    (self.snapshot_limit,),
                )
                if len(self._snapshot_ids) > self.snapshot_limit:
                    self._snapshot_ids = {row[0] for row in self.db.execute("SELECT id FROM snapshots")}
        return snapshot

    def save(self, memory: RunMemory) -> str:
        """Backward-compatible persistence plus a complete run-only snapshot."""
        self.persist(memory)
        return self.snapshot({"schema_version": 1, "run": memory.model_dump(mode="json")})

    def load_snapshot(self, snapshot_id: str) -> dict | None:
        row = self.db.execute("SELECT payload FROM snapshots WHERE id=?", (snapshot_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def close(self):
        self.db.close()
