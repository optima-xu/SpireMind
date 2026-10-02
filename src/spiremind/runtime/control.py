"""Local cooperative controls, bound to the current writer's unique session."""

import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .locking import SingleWriter


def read_control(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def writer_active(lock: Path) -> bool:
    try:
        with SingleWriter(lock):
            return False
    except RuntimeError:
        return True


def request_control(path: Path, lock: Path, mode: str) -> dict:
    if mode not in {"running", "paused"}:
        raise ValueError("Unsupported control request")
    current = read_control(path)
    if not writer_active(lock) or current.get("status") not in {"running", "paused"}:
        raise ValueError("No controllable agent is running. Use start or resume after it has stopped.")
    identity = current.get("session_id")
    if not isinstance(identity, str) or not identity:
        raise ValueError("The running process has no control session; stop it and update SpireMind.")
    _write(path.with_suffix(".request.json"), {"session_id": identity, "mode": mode})
    return {"status": "pause_requested" if mode == "paused" else "resume_requested"}


def control_status(path: Path, lock: Path) -> dict:
    current = read_control(path)
    active = writer_active(lock)
    request = read_control(path.with_suffix(".request.json"))
    return current | {
        "active": active,
        "status": current.get("status", "unknown") if active else "stopped",
        "requested_status": request.get("mode")
        if request.get("session_id") == current.get("session_id")
        else None,
    }


class RunControl:
    def __init__(self, path: Path, settings: dict):
        self.path, self.settings = path, settings
        self.session_id = uuid4().hex
        self.desired = "running"
        self.paused_seconds = 0.0

    def _publish(self, status):
        _write(
            self.path,
            {
                "session_id": self.session_id,
                "status": status,
                "settings": self.settings,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )

    def __enter__(self):
        self._publish("running")
        return self

    def __exit__(self, *args):
        self._publish("stopped")

    def _mode(self):
        request = read_control(self.path.with_suffix(".request.json"))
        if request.get("session_id") == self.session_id and request.get("mode") in {"running", "paused"}:
            self.desired = request["mode"]
        return self.desired

    async def checkpoint(self) -> bool:
        if self._mode() != "paused":
            return False
        started = time.monotonic()
        self._publish("paused")
        print("Agent paused. Use spiremind resume to continue, or Ctrl+C to stop.", flush=True)
        try:
            while self._mode() == "paused":  # noqa: ASYNC110 - another process writes the control file
                await asyncio.sleep(0.1)
        finally:
            self.paused_seconds += time.monotonic() - started
        self._publish("running")
        print("Agent resumed; reading the current game state.", flush=True)
        return True
