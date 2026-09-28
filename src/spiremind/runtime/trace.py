import hashlib
import json
import platform
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from uuid import uuid4


def source_fingerprint() -> str:
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    sources = (
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".py", ".yaml", ".yml", ".json"}
    )
    for path in sorted(sources):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def package_version() -> str:
    try:
        return version("spiremind")
    except PackageNotFoundError:
        return "uninstalled"


class TraceWriter:
    def __init__(self, root: Path, mode: str, configuration: dict | None = None):
        self.attempt_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8]
        self.path = root / self.attempt_id
        self.path.mkdir(parents=True)
        self.mode = mode
        self.write_json(
            "manifest.json",
            {
                "attempt_id": self.attempt_id,
                "mode": mode,
                "started_at": datetime.now(UTC).isoformat(),
                "runtime": {
                    "package_version": package_version(),
                    "python_version": platform.python_version(),
                    "platform": platform.system(),
                    "source_sha256": source_fingerprint(),
                },
                "configuration": configuration or {},
            },
        )

    def append(self, filename: str, payload: dict):
        with (self.path / filename).open("a", encoding="utf-8") as out:
            out.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    def write_json(self, filename: str, payload: dict):
        temporary = self.path / (filename + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        temporary.replace(self.path / filename)


def replay_summary(path: Path) -> dict:
    decisions_path = path / "decisions.jsonl"
    lines = decisions_path.read_text(encoding="utf-8").splitlines() if decisions_path.exists() else []
    records = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            if index != len(lines) - 1:
                raise
            # A killed process can leave only its final JSONL record truncated.
            break
    errors = sum(bool(r.get("error")) for r in records)
    verified = sum(r.get("verify_ok") is True for r in records)
    summary_path = path / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    return {
        "decisions": len(records),
        "verified": verified,
        "errors": errors,
        "invalid_action_count": sum("invalid_action" in str(r.get("error", "")) for r in records),
        "scenes": sorted({r["scene"] for r in records if "scene" in r}),
        "outcome": summary.get("outcome", "incomplete"),
        "floor": summary.get("floor"),
        "mode": summary.get("mode", "unknown"),
    }
