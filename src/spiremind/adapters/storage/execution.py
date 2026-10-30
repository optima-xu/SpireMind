"""Atomic application journal; the game adapter separately owns transport leases."""

import json
import os
from pathlib import Path

from spiremind.core.files import replace_file


class ExecutionJournal:
    def __init__(self, path: Path):
        self.path = path

    def load(self):
        if not self.path.exists():
            return None
        # A corrupt execution journal is not permission to send another action.
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema") != 1:
            raise ValueError("Invalid pending execution journal")
        return value

    def save(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        replace_file(temporary, self.path)

    def clear(self):
        self.path.unlink(missing_ok=True)
