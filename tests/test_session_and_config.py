"""Configuration, API key masking, RunTracker validation, and AgentSession walkthrough tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from spiremind.agent.context import RunTracker
from spiremind.agent.session import AgentSession, validate_entry
from spiremind.config import (
    Config,
    api_key_status,
    canonical_bridge_url,
    load_config,
    safe_extra_body,
    save_settings,
)
from spiremind.domain.decision import StrategyUpdate
from spiremind.domain.state import Action, ActionKind, Card, GameState, PublicFacts, RunState, Scene
from spiremind.knowledge.loader import CardDB
from tests.helpers import MockEnvironment, demo_states


def test_config_ignores_removed_legacy_sections_and_loads_literal_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SPIREMIND_MODEL", raising=False)
    monkeypatch.setenv("PROCESS_VAR", "from-process")
    monkeypatch.delenv("FILE_VAR", raising=False)

    (tmp_path / ".env").write_text(
        '\ufeffPROCESS_VAR="overridden"\nFILE_VAR=literal$(expr) # comment\n',
        encoding="utf-8",
    )
    (tmp_path / "config.local.toml").write_text(
        '[model]\nmodel = "deepseek-chat"\n\n[memory]\nenabled = true\n',
        encoding="utf-8",
    )

    cfg = load_config(None)
    assert cfg.model.model == "deepseek-chat"
    assert os.environ["PROCESS_VAR"] == "from-process"
    assert os.environ["FILE_VAR"] == "literal$(expr)"

    (tmp_path / ".env").write_text("bad line with secret-value\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1") as exc:
        load_config(None)
    assert "secret-value" not in str(exc.value)


def test_save_settings_masks_api_key_and_redacts_extra_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CUSTOM_KEY_ENV", "")
    cfg_path = tmp_path / "config.local.toml"
    env_path = tmp_path / ".env"
    env_path.write_text("# comment\nOTHER=1\n", encoding="utf-8")

    cfg = Config.model_validate(
        {
            "model": {"model": "deepseek-chat", "api_key_env": "CUSTOM_KEY_ENV"},
            "game": {"character": "silent", "ascension": 3},
        }
    )
    save_settings(cfg, cfg_path, env_path, new_api_key="sk-1234567890abcd")

    reloaded = load_config(cfg_path, env_path=env_path)
    assert reloaded.model.model == "deepseek-chat"
    assert reloaded.game.character == "silent"
    assert reloaded.game.ascension == 3

    status = api_key_status("CUSTOM_KEY_ENV")
    assert status == {"env_var": "CUSTOM_KEY_ENV", "configured": True, "masked": "sk-1****abcd"}
    assert "OTHER=1" in env_path.read_text(encoding="utf-8")

    assert safe_extra_body({"enable_thinking": False, "nested": {"api_key": "x", "mode": "safe"}}) == {
        "enable_thinking": False,
        "nested": {"mode": "safe"},
    }
    assert canonical_bridge_url("HTTP://LOCALHOST:80/mcp/") == "http://localhost"


def test_validate_entry_rules(states: list[GameState]) -> None:
    validate_entry(states[0], "start")
    with pytest.raises(ValueError, match="main menu"):
        validate_entry(states[4], "start")

    saved = states[0].model_copy(
        update={
            "legal_actions": states[0].legal_actions
            + (Action(id="continue", decision_id=states[0].decision_id, kind=ActionKind.CONTINUE_RUN),)
        }
    )
    with pytest.raises(ValueError, match="attach"):
        validate_entry(saved, "start")
    validate_entry(saved, "attach")
    with pytest.raises(ValueError, match="No active"):
        validate_entry(states[0], "attach")


async def test_run_tracker_rejects_unsupported_strength_claim_in_boss_plan(tmp_path: Path) -> None:
    db = CardDB(tmp_path / "cards.sqlite")
    from spiremind.domain.state import CardFact

    db.put_many(
        [
            CardFact(
                card_id="pommel_strike",
                game_version="v0.111.0",
                source_version="test",
                text="Deal 9 damage. Draw 1 card.",
                cost=1,
                type="attack",
                values=PublicFacts.of({"Damage": 9, "Cards": 1}),
            )
        ]
    )
    tracker = RunTracker(cards=db)
    card = Card(id="pommel_strike", ref="c0", type="attack", cost=1, name="Pommel Strike")
    shop = GameState(
        scene=Scene.SHOP,
        decision_id="s-1",
        revision=1,
        game_version="v0.111.0",
        run=RunState(id="run-1", floor=5, hp=60, max_hp=80, deck=(card,), boss="Guardian"),
        legal_actions=(Action(id="shop:proceed", decision_id="s-1", kind=ActionKind.PROCEED),),
    )
    next_state = shop.model_copy(update={"decision_id": "s-2", "revision": 2})
    audit = tracker.update(
        shop,
        shop.legal_actions[0],
        next_state,
        StrategyUpdate(boss_plan="Stack Strength using Pommel Strike"),
    )
    assert audit is not None
    assert audit["rejected"]["boss_plan"] == "unsupported_strength_source"
    db.close()


@pytest.mark.parametrize("from_menu", [True, False])
async def test_agent_session_complete_walkthrough_writes_unified_trace(
    tmp_path: Path, from_menu: bool
) -> None:
    cfg = Config.model_validate({"runtime": {"runs_dir": str(tmp_path), "step_delay_seconds": 0}})
    sequence = demo_states() if from_menu else demo_states()[2:]
    env = MockEnvironment(sequence)
    session = AgentSession(cfg)

    summary = await session.run_until_done(
        run_mode="start" if from_menu else "attach",
        policy="rules",
        env=env,
        validate_initial=True,
    )
    assert summary["complete"] is True
    assert summary["outcome"] == "death"
    assert summary["steps"] == len(env.executed) == len(sequence) - 1
    assert session.status == "idle"

    trace_dir = tmp_path / session.attempt_id
    steps = [
        json.loads(line) for line in (trace_dir / "steps.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(steps) == len(sequence) - 1
    assert all(s["verify_ok"] for s in steps)
    assert json.loads((trace_dir / "summary.json").read_text(encoding="utf-8"))["outcome"] == "death"
