import asyncio
import json
from types import SimpleNamespace

import pytest

from spiremind.cli import build_parser, execute, load_cli_config, validate_entry
from spiremind.config import Config, GameConfig
from spiremind.context.budget import ContextBudget
from spiremind.context.compiler import ContextCompiler
from spiremind.core.actions import Action
from spiremind.core.decision import ModelChoice
from spiremind.core.enums import ActionKind
from spiremind.core.state import PublicFacts
from spiremind.environment.mock import MockEnvironment
from spiremind.knowledge.cards import CardDB
from spiremind.knowledge.library import StrategyLibrary
from spiremind.memory.manager import MemoryManager
from spiremind.memory.storage_sqlite import MemoryStore
from spiremind.runtime.agent import AgentRuntime, DecisionInterrupted
from spiremind.runtime.control import RunControl, control_status, request_control
from spiremind.runtime.lifecycle import lifecycle_decision
from spiremind.runtime.locking import SingleWriter
from spiremind.runtime.router import SceneRouter
from spiremind.runtime.trace import TraceWriter
from spiremind.strategies.combat import CombatStrategy
from spiremind.strategies.event import EventStrategy
from spiremind.strategies.fallback import conservative_choice
from spiremind.strategies.map import MapStrategy
from spiremind.strategies.run import DeckAnalyzer, RunStrategy


def test_local_config_and_literal_env_preserve_process_values(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SPIREMIND_MODEL", raising=False)
    monkeypatch.delenv("SPIREMIND_BASE_URL", raising=False)
    monkeypatch.setenv("TEST_KEY", "process-value")
    monkeypatch.delenv("TEST_NEW", raising=False)
    (tmp_path / "config.local.toml").write_text('[model]\nmodel="local-model"\n', encoding="utf-8")
    (tmp_path / ".env").write_text(
        '\ufeff# example\nTEST_KEY="file-value"\nTEST_NEW=literal$(unused) # comment\n', encoding="utf-8"
    )
    assert load_cli_config(None).model.model == "local-model"
    import os

    assert os.environ["TEST_KEY"] == "process-value"
    assert os.environ["TEST_NEW"] == "literal$(unused)"
    (tmp_path / ".env").write_text("invalid secret-data\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1") as error:
        load_cli_config(None)
    assert "secret-data" not in str(error.value)


def test_start_requires_home_and_preserves_saved_run(states):
    validate_entry(states[0], "start")
    with pytest.raises(ValueError, match="main menu"):
        validate_entry(states[4], "start")
    saved = states[0].model_copy(
        update={
            "legal_actions": states[0].legal_actions
            + (Action(id="continue", decision_id=states[0].decision_id, kind=ActionKind.CONTINUE_RUN),)
        }
    )
    with pytest.raises(ValueError, match="existing run"):
        validate_entry(saved, "start")
    with pytest.raises(ValueError, match="existing run"):
        lifecycle_decision(saved, GameConfig(), new_run=True)
    validate_entry(saved, "resume")
    assert lifecycle_decision(saved, GameConfig()).action.id == "continue"
    with pytest.raises(ValueError, match="No run"):
        validate_entry(states[0], "resume")


def test_exact_role_and_difficulty_are_bound_to_available_actions(states):
    state = states[1]
    selection = Action(
        id="select-silent-5",
        decision_id=state.decision_id,
        kind=ActionKind.SELECT_CHARACTER,
        character="silent",
        ascension=5,
    )
    state = state.model_copy(update={"legal_actions": (selection,)})
    assert lifecycle_decision(state, GameConfig(character="silent", ascension=5)).action == selection
    with pytest.raises(ValueError, match="not available"):
        lifecycle_decision(state, GameConfig(character="silent", ascension=6))


async def test_start_off_home_does_not_initialize_model_or_send_actions(tmp_path, monkeypatch, states):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.toml"
    config_path.write_text('[runtime]\nruns_dir="runs"\n', encoding="utf-8")

    class Bridge(MockEnvironment):
        closed = False

        async def health(self):
            return {}

        async def close(self):
            self.closed = True

        async def card_facts(self):
            pytest.fail("Card export must follow entry validation")

    bridge = Bridge(states[4:])
    monkeypatch.setattr("spiremind.cli.bridge_lock_path", lambda _: tmp_path / "live.lock")
    monkeypatch.setattr("spiremind.cli.MCPEnvironment", lambda *_: bridge)
    monkeypatch.setattr(
        "spiremind.cli.OpenAIProvider", lambda *_: pytest.fail("No model request before entry")
    )
    with pytest.raises(ValueError, match="请先返回"):
        await execute(build_parser().parse_args(["--config", str(config_path), "start"]))
    assert bridge.closed and bridge.executed == []


async def test_control_requires_active_writer_and_ignores_old_session(tmp_path):
    path, lock = tmp_path / "control.json", tmp_path / "live.lock"
    with SingleWriter(lock), RunControl(path, {}) as control:
        request_control(path, lock, "paused")
        assert control_status(path, lock)["active"]
        old_id = control.session_id
    assert control_status(path, lock)["status"] == "stopped"
    with pytest.raises(ValueError, match="No controllable"):
        request_control(path, lock, "paused")
    with SingleWriter(lock), RunControl(path, {}) as replacement:
        assert replacement.session_id != old_id
        assert await replacement.checkpoint() is False


async def test_pause_during_decision_discards_choice_and_reads_current_state(tmp_path, states):
    library = StrategyLibrary()
    store = MemoryStore(tmp_path / "memory.sqlite")
    cards = CardDB(tmp_path / "cards.sqlite")
    env = MockEnvironment(states[2:])
    ready, release = asyncio.Event(), asyncio.Event()

    class Provider:
        calls = 0

        async def choose(self, context, legal_ids):
            self.calls += 1
            if self.calls == 1:
                ready.set()
                await release.wait()
            return SimpleNamespace(
                choice=ModelChoice(action_id=sorted(legal_ids)[0], reason="fixture", confidence=1),
                model="offline",
                input_tokens=0,
                output_tokens=0,
                calculations=(),
            )

    compiler = ContextCompiler(library, cards, ContextBudget())
    provider = Provider()
    router = SceneRouter(
        *[
            cls(compiler, provider, conservative_choice)
            for cls in (CombatStrategy, RunStrategy, MapStrategy, EventStrategy)
        ]
    )
    path, lock = tmp_path / "control.json", tmp_path / "live.lock"
    try:
        with SingleWriter(lock), RunControl(path, {}) as control:
            trace = TraceWriter(tmp_path / "traces", "test")
            agent = AgentRuntime(
                env, MemoryManager(store), router, DeckAnalyzer(library), trace, Config(), control=control
            )
            task = asyncio.create_task(agent.step())
            await asyncio.wait_for(ready.wait(), 2)
            request_control(path, lock, "paused")
            release.set()
            async with asyncio.timeout(2):
                while control_status(path, lock)["status"] != "paused":  # noqa: ASYNC110 - observe external file
                    await asyncio.sleep(0.01)
            assert env.executed == []
            env.index = 1  # The player changed the visible game state while paused.
            request_control(path, lock, "running")
            with pytest.raises(DecisionInterrupted):
                await asyncio.wait_for(task, 2)
            assert env.executed == []
            await agent.step()
            assert env.executed[0].decision_id == states[3].decision_id
            rows = [json.loads(x) for x in (trace.path / "decisions.jsonl").read_text().splitlines()]
            assert rows[0]["discarded_on_resume"] and not rows[0]["verify_ok"]
            assert rows[1]["verify_ok"]
    finally:
        cards.close()
        store.close()


async def test_cli_resume_signals_running_process_without_model_or_launch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path, lock = tmp_path / "live.control.json", tmp_path / "live.lock"
    monkeypatch.setattr("spiremind.cli.bridge_lock_path", lambda _: lock)
    monkeypatch.setattr(
        "spiremind.cli.MCPEnvironment", lambda *_: pytest.fail("Must not launch another writer")
    )
    with SingleWriter(lock), RunControl(path, {}):
        assert (await execute(build_parser().parse_args(["pause"])))["status"] == "pause_requested"
        assert (await execute(build_parser().parse_args(["resume"])))["status"] == "resume_requested"
        with pytest.raises(ValueError, match="Omit launch"):
            await execute(build_parser().parse_args(["resume", "--policy", "rules"]))


async def test_stopped_resume_restores_role_difficulty_and_policy(tmp_path, monkeypatch, states):
    monkeypatch.chdir(tmp_path)
    path, lock = tmp_path / "live.control.json", tmp_path / "live.lock"
    settings = {"character": "silent", "ascension": 5, "policy": "rules"}
    with SingleWriter(lock), RunControl(path, settings):
        pass
    selected = states[1].model_copy(
        update={"scene_facts": PublicFacts.of({"selected_character_id": "silent", "ascension": 5})}
    )

    class Bridge(MockEnvironment):
        game_version = "v0.111.0"
        closed = False

        async def health(self):
            return {"game_version": self.game_version}

        async def card_facts(self):
            return []

        async def close(self):
            self.closed = True

    bridge = Bridge([selected, states[2], states[-1]])

    def connect(config, _):
        assert (config.character, config.ascension) == ("silent", 5)
        return bridge

    monkeypatch.setattr("spiremind.cli.bridge_lock_path", lambda _: lock)
    monkeypatch.setattr("spiremind.cli.MCPEnvironment", connect)
    monkeypatch.setattr(
        "spiremind.cli.OpenAIProvider", lambda *_: pytest.fail("Resume must restore the rules policy")
    )
    result = await execute(build_parser().parse_args(["resume"]))
    assert result["complete"] and result["verified_actions"] == 2
    assert bridge.closed and control_status(path, lock)["status"] == "stopped"
