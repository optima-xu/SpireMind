"""TraceWriter (`steps.jsonl`) and legacy-compatible TraceReader tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from spiremind.storage.trace_store import ATTEMPT_RE, TraceReader, TraceWriter


def test_trace_writer_and_reader_round_trip_with_redaction_and_truncated_tail(tmp_path: Path) -> None:
    writer = TraceWriter(
        tmp_path,
        "ui_model",
        configuration={
            "model": {
                "model": "deepseek-chat",
                "extra_body": {"thinking": {"type": "disabled"}, "api_key": "secret-val"},
            },
            "game": {"character": "ironclad", "ascension": 2},
        },
    )
    assert ATTEMPT_RE.match(writer.attempt_id)

    writer.record_step(
        {
            "step": 1,
            "decision_id": "d-1",
            "revision": 1,
            "scene": "combat",
            "state": {
                "decision_id": "d-1",
                "revision": 1,
                "scene": "combat",
                "game_version": "v0.111.0",
                "run": {
                    "id": "seed",
                    "character": "ironclad",
                    "ascension": 2,
                    "hp": 72,
                    "max_hp": 80,
                    "floor": 3,
                },
            },
            "decision": {"action": {"id": "play:0"}, "reason": "Block", "confidence": 0.9},
            "verify_ok": True,
            "latency_ms": 120,
            "input_tokens": 50,
            "output_tokens": 12,
        }
    )
    # Append a partial truncated tail simulating crash before newline/flush finished
    with (writer.path / "steps.jsonl").open("a", encoding="utf-8") as stream:
        stream.write('{"step": 2, "broken_json')

    writer.finish(
        {
            "outcome": "death",
            "steps": 1,
            "character": "ironclad",
            "ascension": 2,
            "floor": 3,
            "hp": 0,
            "max_hp": 80,
            "game_version": "v0.111.0",
        }
    )

    reader = TraceReader(tmp_path)
    runs = reader.list_runs()
    assert len(runs) == 1
    assert runs[0]["attempt_id"] == writer.attempt_id
    assert runs[0]["format"] == "steps_v2"
    assert runs[0]["model"] == "deepseek-chat"
    assert runs[0]["outcome"] == "death"

    detail = reader.get_run(writer.attempt_id)
    assert "secret-val" not in json.dumps(detail["manifest"])
    assert len(detail["steps"]) == 1
    assert detail["steps"][0]["decision"]["reason"] == "Block"


def test_trace_reader_parses_legacy_states_and_decisions_and_rejects_traversal(tmp_path: Path) -> None:
    legacy = tmp_path / "20261003T120930-d4397bc3"
    legacy.mkdir()
    (legacy / "manifest.json").write_text(
        json.dumps(
            {"attempt_id": legacy.name, "mode": "legacy_run", "configuration": {"model": {"model": "m"}}}
        ),
        encoding="utf-8",
    )
    (legacy / "states.jsonl").write_text(
        json.dumps(
            {
                "decision_id": "dec-1",
                "revision": 1,
                "scene": "event",
                "game_version": "v0.111.0",
                "run": {"character": "ironclad", "hp": 65, "max_hp": 80, "floor": 1},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (legacy / "decisions.jsonl").write_text(
        json.dumps(
            {
                "decision_id": "dec-1",
                "state_revision": 1,
                "scene": "event",
                "action": {"id": "event:option:0", "kind": "choose_event_option", "label": "Leave"},
                "reason": "Legacy reason",
                "confidence": 0.88,
                "verify_ok": True,
                "input_tokens": 30,
                "output_tokens": 10,
            }
        )
        + "\n{truncated",
        encoding="utf-8",
    )

    # Unrelated folders must never appear in run listings
    (tmp_path / "wheel-smoke").mkdir()

    reader = TraceReader(tmp_path)
    runs = reader.list_runs()
    assert [r["attempt_id"] for r in runs] == ["20261003T120930-d4397bc3"]
    assert runs[0]["format"] == "legacy_v1"

    detail = reader.get_run("20261003T120930-d4397bc3")
    assert len(detail["steps"]) == 1
    assert detail["steps"][0]["decision"]["reason"] == "Legacy reason"
    assert detail["steps"][0]["verify_ok"] is True

    with pytest.raises(ValueError, match="Invalid attempt_id"):
        reader.get_run("../secrets")

    with pytest.raises(FileNotFoundError):
        reader.get_run("20261003T120930-ffffffff")
