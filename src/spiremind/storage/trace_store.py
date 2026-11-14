"""Unified step-level trace writer and legacy-compatible run history reader."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any
from uuid import uuid4

from spiremind.config import safe_extra_body
from spiremind.domain.safety import replace_file

ATTEMPT_RE = re.compile(r"^\d{8}T\d{6}-[a-f0-9]{8}$")


def package_version() -> str:
    try:
        return pkg_version("spiremind")
    except PackageNotFoundError:
        return "0.2.0"


def source_fingerprint() -> str:
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    replace_file(tmp, path)


def _read_json_safe(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _parse_jsonl_tolerant(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    rows: list[dict[str, Any]] = []
    non_empty = [line for line in lines if line.strip()]
    total = len(non_empty)
    for idx, line in enumerate(non_empty):
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        except json.JSONDecodeError:
            # Tolerate a crash-truncated final record; skip corrupted lines cleanly.
            if idx == total - 1:
                break
    return rows


def _iso_from_attempt(attempt_id: str) -> str:
    try:
        dt = datetime.strptime(attempt_id[:15], "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
        return dt.isoformat()
    except ValueError:
        return ""


class TraceWriter:
    """Writes one unified `steps.jsonl` trace plus `manifest.json`, `progress.json`, and `summary.json`."""

    def __init__(
        self,
        root: Path | str,
        mode: str,
        configuration: dict[str, Any] | None = None,
        *,
        attempt_id: str | None = None,
    ) -> None:
        self.root = Path(root)
        self.mode = mode
        self.attempt_id = attempt_id or f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid4().hex[:8]}"
        self.path = self.root / self.attempt_id
        self.path.mkdir(parents=True, exist_ok=True)
        self._steps_path = self.path / "steps.jsonl"
        self.steps_written = 0

        manifest = {
            "schema_version": 2,
            "attempt_id": self.attempt_id,
            "created_at": datetime.now(UTC).isoformat(),
            "mode": mode,
            "configuration": safe_extra_body(configuration) if configuration is not None else {},
            "runtime": {
                "package_version": package_version(),
                "source_sha256": source_fingerprint(),
            },
        }
        _write_json_atomic(self.path / "manifest.json", manifest)

    def record_step(self, step: dict[str, Any]) -> None:
        self.steps_written += 1
        with self._steps_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(step, ensure_ascii=False, default=str) + "\n")
            stream.flush()

        state = step.get("state") or {}
        run = state.get("run") or {}
        progress = {
            "attempt_id": self.attempt_id,
            "steps_count": self.steps_written,
            "scene": step.get("scene") or state.get("scene"),
            "character": run.get("character"),
            "ascension": run.get("ascension"),
            "game_version": state.get("game_version"),
            "act": run.get("act"),
            "floor": run.get("floor"),
            "hp": run.get("hp"),
            "max_hp": run.get("max_hp"),
            "gold": run.get("gold"),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        _write_json_atomic(self.path / "progress.json", progress)

    def finish(self, summary: dict[str, Any]) -> None:
        payload = {"attempt_id": self.attempt_id, "finished_at": datetime.now(UTC).isoformat(), **summary}
        _write_json_atomic(self.path / "summary.json", payload)


class TraceReader:
    """Reads both new `steps.jsonl` traces and legacy `states.jsonl + decisions.jsonl` runs."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _run_dirs(self) -> list[Path]:
        if not self.root.exists():
            return []
        dirs = [p for p in self.root.iterdir() if p.is_dir() and ATTEMPT_RE.match(p.name)]
        return sorted(dirs, key=lambda p: p.name, reverse=True)

    @staticmethod
    def _legacy_decision_payload(dec: dict[str, Any]) -> dict[str, Any]:
        # Normalizes both legacy decision rows and v2 decision blocks.
        return {
            "action": dec.get("action"),
            "reason": dec.get("reason", ""),
            "confidence": dec.get("confidence", 0),
            "strategy_name": dec.get("strategy_name"),
            "policy_rule": dec.get("policy_rule"),
            "model_name": dec.get("model_name"),
            "calculations": dec.get("calculations") or [],
            "fallback": bool(dec.get("fallback", False)),
            "provider_error": dec.get("provider_error"),
            "strategy_update": dec.get("strategy_update"),
            "strategy_update_audit": dec.get("strategy_update_audit"),
            "combat_assessment": dec.get("combat_assessment"),
        }

    def _summarize_dir(self, run_dir: Path) -> dict[str, Any]:
        manifest = _read_json_safe(run_dir / "manifest.json") or {}
        summary = _read_json_safe(run_dir / "summary.json")
        progress = _read_json_safe(run_dir / "progress.json") or {}
        config = manifest.get("configuration") or {}
        model_cfg = config.get("model") if isinstance(config.get("model"), dict) else {}
        game_cfg = config.get("game") if isinstance(config.get("game"), dict) else {}

        has_v2 = (run_dir / "steps.jsonl").exists()
        has_legacy = (run_dir / "states.jsonl").exists()
        fmt = "steps_v2" if has_v2 else ("legacy_v1" if has_legacy else "empty")

        meta = summary or progress
        steps_count = meta.get("steps_count") or meta.get("steps")
        character = meta.get("character") or game_cfg.get("character")
        ascension = meta.get("ascension") if meta.get("ascension") is not None else game_cfg.get("ascension")
        floor = meta.get("floor")
        hp = meta.get("hp")
        max_hp = meta.get("max_hp")
        game_version = meta.get("game_version")
        outcome = (summary or {}).get("outcome") or ("in_progress" if not summary and steps_count else None)

        if steps_count is None:
            if has_v2:
                rows = _parse_jsonl_tolerant(run_dir / "steps.jsonl")
                steps_count = len(rows)
                if rows:
                    last_state = rows[-1].get("state") or {}
                    last_run = last_state.get("run") or {}
                    character = character or last_run.get("character")
                    ascension = ascension if ascension is not None else last_run.get("ascension")
                    floor = floor if floor is not None else last_run.get("floor")
                    hp = hp if hp is not None else last_run.get("hp")
                    max_hp = max_hp if max_hp is not None else last_run.get("max_hp")
                    game_version = game_version or last_state.get("game_version")
            elif has_legacy:
                states = _parse_jsonl_tolerant(run_dir / "states.jsonl")
                steps_count = len(states)
                if states:
                    last_state = states[-1]
                    last_run = last_state.get("run") or {}
                    character = character or last_run.get("character")
                    ascension = ascension if ascension is not None else last_run.get("ascension")
                    floor = floor if floor is not None else last_run.get("floor")
                    hp = hp if hp is not None else last_run.get("hp")
                    max_hp = max_hp if max_hp is not None else last_run.get("max_hp")
                    game_version = game_version or last_state.get("game_version")

        return {
            "attempt_id": run_dir.name,
            "created_at": manifest.get("created_at") or _iso_from_attempt(run_dir.name),
            "mode": manifest.get("mode") or "unknown",
            "model": model_cfg.get("model"),
            "character": character,
            "ascension": ascension,
            "game_version": game_version,
            "outcome": outcome or "incomplete",
            "floor": floor,
            "hp": hp,
            "max_hp": max_hp,
            "steps_count": steps_count or 0,
            "format": fmt,
        }

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        return [self._summarize_dir(run_dir) for run_dir in self._run_dirs()[:limit]]

    def get_run(self, attempt_id: str) -> dict[str, Any]:
        if not ATTEMPT_RE.match(attempt_id):
            raise ValueError(f"Invalid attempt_id: {attempt_id}")
        run_dir = self.root / attempt_id
        if not run_dir.is_dir():
            raise FileNotFoundError(attempt_id)

        manifest = _read_json_safe(run_dir / "manifest.json") or {"attempt_id": attempt_id}
        summary_data = (
            _read_json_safe(run_dir / "summary.json") or _read_json_safe(run_dir / "progress.json") or {}
        )
        meta = self._summarize_dir(run_dir)

        steps: list[dict[str, Any]] = []
        v2_path = run_dir / "steps.jsonl"
        legacy_states_path = run_dir / "states.jsonl"

        if v2_path.exists():
            for idx, row in enumerate(_parse_jsonl_tolerant(v2_path), start=1):
                steps.append(
                    {
                        "step": row.get("step", idx),
                        "timestamp": row.get("timestamp"),
                        "decision_id": row.get("decision_id"),
                        "revision": row.get("revision"),
                        "scene": row.get("scene"),
                        "state": row.get("state"),
                        "decision": row.get("decision"),
                        "combat_assessment": row.get("combat_assessment"),
                        "run_context": row.get("run_context"),
                        "receipt": row.get("receipt"),
                        "verify_ok": row.get("verify_ok"),
                        "latency_ms": row.get("latency_ms"),
                        "input_tokens": row.get("input_tokens", 0),
                        "output_tokens": row.get("output_tokens", 0),
                        "error": row.get("error"),
                    }
                )
        elif legacy_states_path.exists():
            states = _parse_jsonl_tolerant(legacy_states_path)
            decisions = _parse_jsonl_tolerant(run_dir / "decisions.jsonl")
            by_pair: dict[tuple[str, int | None], dict[str, Any]] = {}
            by_id: dict[str, dict[str, Any]] = {}
            for dec in decisions:
                did = dec.get("decision_id")
                rev = dec.get("state_revision")
                if isinstance(did, str):
                    by_pair[(did, rev)] = dec
                    by_id.setdefault(did, dec)

            for idx, st in enumerate(states, start=1):
                did = st.get("decision_id")
                rev = st.get("revision")
                dec = by_pair.get((did, rev)) if isinstance(did, str) else None
                if dec is None and isinstance(did, str):
                    dec = by_id.get(did)
                steps.append(
                    {
                        "step": idx,
                        "timestamp": st.get("captured_at") or (dec or {}).get("recorded_at"),
                        "decision_id": did,
                        "revision": rev,
                        "scene": st.get("scene") or (dec or {}).get("scene"),
                        "state": st,
                        "decision": self._legacy_decision_payload(dec) if dec else None,
                        "combat_assessment": None,
                        "run_context": None,
                        "receipt": None,
                        "verify_ok": dec.get("verify_ok") if dec else None,
                        "latency_ms": dec.get("latency_ms") if dec else None,
                        "input_tokens": dec.get("input_tokens", 0) if dec else 0,
                        "output_tokens": dec.get("output_tokens", 0) if dec else 0,
                        "error": dec.get("error") if dec else None,
                    }
                )

        return {
            "attempt_id": attempt_id,
            "meta": meta,
            "manifest": manifest,
            "summary": summary_data,
            "steps": steps,
        }
