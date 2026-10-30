import asyncio
import json

import pytest

from spiremind.adapters.locking import SingleWriter
from spiremind.adapters.storage.cards import CardDB
from spiremind.adapters.storage.memory import MemoryStore
from spiremind.adapters.telemetry.trace import TraceWriter, replay_summary
from spiremind.application.run_state import MemoryManager
from spiremind.application.session import AgentRuntime, ProviderFallbackLimit, ProviderRetryPending
from spiremind.config import Config
from spiremind.core.actions import Action, ActionResult
from spiremind.core.budget import ContextBudget
from spiremind.core.decision import Decision, StrategyUpdate
from spiremind.core.enums import ActionKind, Scene
from spiremind.core.ports import EnvironmentError, StaleDecision
from spiremind.core.validation import ActionValidator
from spiremind.decision.context import ContextCompiler
from spiremind.decision.deck import DeckAnalyzer
from spiremind.decision.policies.combat import CombatStrategy
from spiremind.decision.policies.event import EventStrategy
from spiremind.decision.policies.fallback import conservative_choice
from spiremind.decision.policies.lifecycle import lifecycle_decision
from spiremind.decision.policies.map import MapStrategy
from spiremind.decision.policies.run import RunStrategy
from spiremind.decision.router import SceneRouter
from spiremind.evaluation.mock import MockEnvironment, demo_states
from spiremind.knowledge.library import StrategyLibrary


def test_total_token_budget_is_unlimited_by_default():
    assert Config().runtime.max_total_tokens is None
    assert Config.model_validate({"runtime": {"max_total_tokens": 100}}).runtime.max_total_tokens == 100


def test_wall_clock_limit_is_unlimited_by_default():
    assert Config().runtime.max_seconds is None
    assert Config.model_validate({"runtime": {"max_seconds": 600}}).runtime.max_seconds == 600


def test_forged_and_stale_commands(states):
    validator = ActionValidator()
    state = states[4]
    with pytest.raises(ValueError):
        validator.validate(state, state.legal_actions[0].model_copy(update={"target_id": "invented"}))
    with pytest.raises(StaleDecision):
        validator.validate(states[5], state.legal_actions[0])


def test_process_lock(tmp_path):
    lock = tmp_path / "lock"
    with SingleWriter(lock) as owner:
        assert owner.path.is_absolute()
        with pytest.raises(RuntimeError), SingleWriter(tmp_path / "lock"):
            pass
    with SingleWriter(lock):
        pass
    assert lock.stat().st_size == 1


def test_trace_manifest_records_reproducible_nonsecret_configuration(tmp_path):
    trace = TraceWriter(
        tmp_path,
        "test",
        configuration={"model": {"model": "m", "enable_thinking": True}},
    )
    manifest = json.loads((trace.path / "manifest.json").read_text())
    assert manifest["configuration"]["model"] == {"model": "m", "enable_thinking": True}
    assert len(manifest["runtime"]["source_sha256"]) == 64
    assert "api_key" not in json.dumps(manifest).lower()


@pytest.mark.parametrize("from_menu", [True, False])
async def test_complete_runtime_and_trace(tmp_path, from_menu):
    store, db = MemoryStore(tmp_path / "m.sqlite"), CardDB(tmp_path / "c.sqlite")
    library = StrategyLibrary()
    compiler = ContextCompiler(library, db, ContextBudget())
    router = SceneRouter(
        *[
            c(compiler, None, conservative_choice)
            for c in (CombatStrategy, RunStrategy, MapStrategy, EventStrategy)
        ]
    )
    trace = TraceWriter(tmp_path / "runs", "mock_rules")
    env = MockEnvironment(None if from_menu else demo_states()[2:])
    agent = AgentRuntime(env, MemoryManager(store), router, DeckAnalyzer(library), trace, Config())
    result = await agent.run()
    assert result["complete"] and result["outcome"] == "death"
    assert result["full_lifecycle_complete"] == from_menu
    assert result["verified_actions"] == len(env.executed) == len(env.states) - 1
    records = [json.loads(x) for x in (trace.path / "decisions.jsonl").read_text().splitlines()]
    assert all(r["verify_ok"] for r in records)
    assert all((r["memory_snapshot_id"] is None) == (r["strategy_name"] == "lifecycle") for r in records)
    assert {r["strategy_name"] for r in records} == {"combat", "map", "run", "event"} | (
        {"lifecycle"} if from_menu else set()
    )
    assert replay_summary(trace.path)["verified"] == len(env.states) - 1
    traced_states = [json.loads(x) for x in (trace.path / "states.jsonl").read_text().splitlines()]
    assert [state["decision_id"] for state in traced_states] == [state.decision_id for state in env.states]
    assert json.loads((trace.path / "final-state.json").read_text())["scene"] == "game_over"
    assert agent.memory.run.outcome == "death"
    db.close()
    store.close()


def test_replay_accepts_no_decisions_and_a_truncated_tail(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "summary.json").write_text('{"outcome":"death","floor":3}', encoding="utf-8")
    assert replay_summary(empty) == {
        "decisions": 0,
        "verified": 0,
        "errors": 0,
        "invalid_action_count": 0,
        "scenes": [],
        "outcome": "death",
        "floor": 3,
        "mode": "unknown",
    }

    truncated = tmp_path / "truncated"
    truncated.mkdir()
    (truncated / "decisions.jsonl").write_text(
        '{"scene":"combat","verify_ok":true}\n{"scene":', encoding="utf-8"
    )
    result = replay_summary(truncated)
    assert result["decisions"] == result["verified"] == 1
    assert result["scenes"] == ["combat"]


def test_unknown_scene_fails_closed(states):
    router = SceneRouter("combat", "run", "map", "event")
    with pytest.raises(ValueError, match="Unsupported scene"):
        router.route(states[2].model_copy(update={"scene": Scene.UNKNOWN}))


def test_lifecycle_closes_a_main_menu_submenu(states):
    state = states[0]
    close = Action(
        id="main_menu:close_submenu",
        decision_id=state.decision_id,
        kind=ActionKind.CLOSE_MENU,
    )
    state = state.model_copy(update={"legal_actions": (close,)})

    decision = lifecycle_decision(state, Config().game)

    assert decision.action == close


async def test_provider_retries_for_180_seconds_without_sending_actions(tmp_path, monkeypatch):
    clock = [0.0]

    async def retry_sleep(seconds):
        clock[0] += 20

    monkeypatch.setattr("spiremind.application.session.asyncio.sleep", retry_sleep)

    class ProviderFailingStrategy:
        name = "event"
        last_context = None

        async def decide(self, state, memory):
            decision = conservative_choice(state, memory)
            decision.provider_error = "provider unavailable"
            return decision

    store = MemoryStore(tmp_path / "m.sqlite")
    library = StrategyLibrary()
    strategy = ProviderFailingStrategy()
    router = SceneRouter(strategy, strategy, strategy, strategy)
    trace = TraceWriter(tmp_path / "runs", "provider_failure")
    env = MockEnvironment(demo_states()[2:])
    config = Config()
    config.runtime.max_errors = 2
    agent = AgentRuntime(env, MemoryManager(store), router, DeckAnalyzer(library), trace, config)
    monkeypatch.setattr(agent, "_recovery_clock", lambda: clock[0])

    result = await agent.run()

    assert result["outcome"] == "error_limit"
    assert result["errors"] == result["max_provider_error_streak"] == 9
    assert result["provider_failure_seconds"] == 180
    assert result["fallbacks"] == result["verified_actions"] == len(env.executed) == 0
    assert json.loads((trace.path / "final-state.json").read_text())["scene"] == "event"
    store.close()


async def test_provider_success_resets_recovery_window(tmp_path, monkeypatch):
    class RecoveringStrategy:
        name = "event"
        last_context = None
        failing = True

        async def decide(self, state, memory):
            decision = conservative_choice(state, memory)
            if self.failing:
                decision.provider_error = "unavailable"
            else:
                decision.context_id = "successful-model-response"
            return decision

    store = MemoryStore(tmp_path / "memory.sqlite")
    strategy = RecoveringStrategy()
    env = MockEnvironment(demo_states()[2:])
    agent = AgentRuntime(
        env,
        MemoryManager(store),
        SceneRouter(strategy, strategy, strategy, strategy),
        DeckAnalyzer(StrategyLibrary()),
        TraceWriter(tmp_path / "runs", "recovery"),
        Config(),
    )
    clock = [10.0]
    monkeypatch.setattr(agent, "_recovery_clock", lambda: clock[0])
    with pytest.raises(ProviderRetryPending):
        await agent.step()
    assert agent.provider_failure_started == 10
    clock[0] = 100
    strategy.failing = False
    await agent.step()
    assert agent.provider_failure_started is None
    assert agent.provider_error_streak == 0
    assert len(env.executed) == 1
    strategy.failing = True
    with pytest.raises(ProviderRetryPending):
        await agent.step()
    assert agent.provider_failure_started == 100
    store.close()


async def test_slow_provider_retry_is_cancelled_at_recovery_deadline(tmp_path):
    class HangingStrategy:
        name = "event"
        last_context = None
        cancelled = False

        async def decide(self, state, memory):
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled = True

    store = MemoryStore(tmp_path / "memory.sqlite")
    strategy = HangingStrategy()
    env = MockEnvironment(demo_states()[2:])
    config = Config()
    config.runtime.error_retry_seconds = 0.2
    agent = AgentRuntime(
        env,
        MemoryManager(store),
        SceneRouter(strategy, strategy, strategy, strategy),
        DeckAnalyzer(StrategyLibrary()),
        TraceWriter(tmp_path / "runs", "deadline"),
        config,
    )
    agent.provider_failure_started = agent._recovery_clock()
    with pytest.raises(ProviderFallbackLimit):
        await asyncio.wait_for(agent.step(), 1)
    assert strategy.cancelled
    assert not env.executed
    store.close()


async def test_recovered_environment_does_not_cancel_a_healthy_slow_model(tmp_path):
    class RecoveredEnvironment(MockEnvironment):
        failed = False

        async def observe(self):
            if not self.failed:
                self.failed = True
                raise EnvironmentError("temporary bridge failure")
            return await super().observe()

    class SlowHealthyStrategy:
        name = "event"
        last_context = None

        async def decide(self, state, memory):
            await asyncio.sleep(0.06)
            return conservative_choice(state, memory)

    store = MemoryStore(tmp_path / "memory.sqlite")
    strategy = SlowHealthyStrategy()
    env = RecoveredEnvironment(demo_states()[2:])
    config = Config()
    config.runtime.max_steps = 1
    config.runtime.error_retry_seconds = 0.03
    agent = AgentRuntime(
        env,
        MemoryManager(store),
        SceneRouter(strategy, strategy, strategy, strategy),
        DeckAnalyzer(StrategyLibrary()),
        TraceWriter(tmp_path / "runs", "recovered"),
        config,
    )
    # Enter recovery without a tiny real-time backoff: CI filesystem/scheduler
    # variation must not consume the entire test window before the retry starts.
    with pytest.raises(EnvironmentError):
        await agent.step()
    agent.environment_failure_started = agent._recovery_clock()
    result = await agent.run()
    assert result["verified_actions"] == len(env.executed) == 1
    assert result["outcome"] == "step_limit"
    assert result["environment_failure_seconds"] == 0
    store.close()


async def test_observation_failure_after_execution_is_reconciled_before_any_new_action(tmp_path):
    class DelayedObservationEnvironment(MockEnvironment):
        fail_next_observe = False

        async def execute(self, action):
            receipt = await super().execute(action)
            self.fail_next_observe = True
            return receipt

        async def observe(self):
            if self.fail_next_observe:
                self.fail_next_observe = False
                raise EnvironmentError("observation unavailable after accepted action")
            return await super().observe()

    class Strategy:
        name = "event"
        last_context = None
        calls = 0

        async def decide(self, state, memory):
            self.calls += 1
            return conservative_choice(state, memory)

    store = MemoryStore(tmp_path / "memory.sqlite")
    strategy = Strategy()
    env = DelayedObservationEnvironment(demo_states()[2:])
    agent = AgentRuntime(
        env,
        MemoryManager(store),
        SceneRouter(strategy, strategy, strategy, strategy),
        DeckAnalyzer(StrategyLibrary()),
        TraceWriter(tmp_path / "runs", "reconcile"),
        Config(),
    )
    with pytest.raises(EnvironmentError):
        await agent.step()
    await agent.step()
    assert agent.verified == len(env.executed) == strategy.calls == 1
    assert agent._pending_transition is None
    assert agent.memory.run.key_decisions
    assert replay_summary(agent.trace.path)["verified"] == 1
    store.close()


async def test_repeated_bad_receipt_stops_without_dispatching_a_second_action(tmp_path, monkeypatch):
    class BadReceiptEnvironment(MockEnvironment):
        async def execute(self, action):
            receipt = await super().execute(action)
            return receipt.model_copy(update={"next_decision_id": "wrong-decision"})

    class Strategy:
        name = "event"
        last_context = None

        async def decide(self, state, memory):
            return conservative_choice(state, memory)

    clock = [0.0]

    async def backoff(seconds):
        clock[0] += 60

    monkeypatch.setattr("spiremind.application.session.asyncio.sleep", backoff)
    store = MemoryStore(tmp_path / "memory.sqlite")
    strategy = Strategy()
    env = BadReceiptEnvironment(demo_states()[2:])
    agent = AgentRuntime(
        env,
        MemoryManager(store),
        SceneRouter(strategy, strategy, strategy, strategy),
        DeckAnalyzer(StrategyLibrary()),
        TraceWriter(tmp_path / "runs", "bad_receipt"),
        Config(),
    )
    monkeypatch.setattr(agent, "_recovery_clock", lambda: clock[0])
    result = await agent.run()
    assert result["outcome"] == "error_limit"
    assert result["environment_recovery_seconds"]["verify"] == 180
    assert len(env.executed) == 1
    assert agent.verified == 0
    assert agent.memory.run.key_decisions == []
    store.close()


async def test_completed_receipt_must_name_the_observed_next_decision(tmp_path):
    class MismatchedReceiptEnvironment(MockEnvironment):
        async def execute(self, action):
            receipt = await super().execute(action)
            return ActionResult(
                status=receipt.status,
                action_id=receipt.action_id,
                previous_decision_id=receipt.previous_decision_id,
                next_decision_id="different-decision",
            )

    store, db = MemoryStore(tmp_path / "m.sqlite"), CardDB(tmp_path / "c.sqlite")
    library = StrategyLibrary()
    compiler = ContextCompiler(library, db, ContextBudget())
    strategies = [
        cls(compiler, None, conservative_choice)
        for cls in (CombatStrategy, RunStrategy, MapStrategy, EventStrategy)
    ]
    trace = TraceWriter(tmp_path / "runs", "mismatch")
    env = MismatchedReceiptEnvironment(demo_states()[2:])
    config = Config()
    config.runtime.max_errors = 1
    config.runtime.error_retry_seconds = 0.001
    agent = AgentRuntime(
        env,
        MemoryManager(store),
        SceneRouter(*strategies),
        DeckAnalyzer(library),
        trace,
        config,
    )

    result = await agent.run()

    assert result["outcome"] == "error_limit"
    assert result["verified_actions"] == 0
    record = json.loads((trace.path / "decisions.jsonl").read_text().splitlines()[0])
    assert record["transition_verified"] is True
    assert record["semantic_success"] is False
    assert record["verify_ok"] is False
    db.close()
    store.close()


async def test_uncertain_receipt_is_reconciled_but_not_semantic_success(tmp_path):
    class UncertainReceiptEnvironment(MockEnvironment):
        async def execute(self, action):
            receipt = await super().execute(action)
            return ActionResult(
                status="uncertain",
                action_id=receipt.action_id,
                previous_decision_id=receipt.previous_decision_id,
            )

    store, db = MemoryStore(tmp_path / "m.sqlite"), CardDB(tmp_path / "c.sqlite")
    library = StrategyLibrary()
    compiler = ContextCompiler(library, db, ContextBudget())
    strategies = [
        cls(compiler, None, conservative_choice)
        for cls in (CombatStrategy, RunStrategy, MapStrategy, EventStrategy)
    ]
    trace = TraceWriter(tmp_path / "runs", "uncertain")
    env = UncertainReceiptEnvironment(demo_states()[2:4])
    config = Config()
    config.runtime.max_steps = 1
    agent = AgentRuntime(
        env,
        MemoryManager(store),
        SceneRouter(*strategies),
        DeckAnalyzer(library),
        trace,
        config,
    )

    result = await agent.run()

    assert result["outcome"] == "step_limit"
    assert result["verified_actions"] == result["reconciled_actions"] == 1
    assert result["semantic_success_actions"] == 0
    record = json.loads((trace.path / "decisions.jsonl").read_text())
    assert record["verify_ok"] is True
    assert record["reconciled_after_uncertain"] is True
    assert record["semantic_success"] is False
    assert agent.memory.run.key_decisions == []
    db.close()
    store.close()


async def test_strategy_update_proposal_and_validation_are_traced(tmp_path):
    class UpdatingStrategy:
        name = "run"
        last_context = None

        async def decide(self, state, memory):
            return Decision(
                action=state.legal_actions[0],
                reason="test update",
                strategy_update=StrategyUpdate(
                    gold_policy="Save for a strong removal.",
                    route_preferences=["Prefer safe nodes"],
                ),
            )

    store = MemoryStore(tmp_path / "m.sqlite")
    strategy = UpdatingStrategy()
    trace = TraceWriter(tmp_path / "runs", "strategy_update")
    config = Config()
    config.runtime.max_steps = 1
    agent = AgentRuntime(
        MockEnvironment(demo_states()[5:7]),
        MemoryManager(store),
        SceneRouter(strategy, strategy, strategy, strategy),
        DeckAnalyzer(StrategyLibrary()),
        trace,
        config,
    )

    await agent.run()

    record = json.loads((trace.path / "decisions.jsonl").read_text())
    assert record["strategy_update"]["gold_policy"] == "Save for a strong removal."
    assert record["strategy_update_audit"]["applied"] == {"gold_policy": "Save for a strong removal."}
    assert record["strategy_update_audit"]["rejected"] == {"route_preferences": "field_owned_by_map"}
    store.close()


async def test_run_can_clear_a_preexisting_terminal_then_start_once(tmp_path):
    terminal_decision = "old-run:game-over"
    terminal = demo_states()[-1].model_copy(
        update={
            "decision_id": terminal_decision,
            "revision": 0,
            "legal_actions": (
                Action(
                    id="game_over:return_to_main_menu",
                    decision_id=terminal_decision,
                    kind=ActionKind.RETURN_TO_MAIN_MENU,
                ),
            ),
        }
    )
    states = (terminal, *demo_states())
    store, db = MemoryStore(tmp_path / "m.sqlite"), CardDB(tmp_path / "c.sqlite")
    library = StrategyLibrary()
    compiler = ContextCompiler(library, db, ContextBudget())
    strategies = [
        cls(compiler, None, conservative_choice)
        for cls in (CombatStrategy, RunStrategy, MapStrategy, EventStrategy)
    ]
    trace = TraceWriter(tmp_path / "runs", "terminal_restart")
    agent = AgentRuntime(
        MockEnvironment(states),
        MemoryManager(store),
        SceneRouter(*strategies),
        DeckAnalyzer(library),
        trace,
        Config(),
    )

    result = await agent.run()

    assert result["started_scene"] == "game_over"
    assert result["started_new_run"] is True
    assert result["full_lifecycle_complete"] is True
    records = [json.loads(line) for line in (trace.path / "decisions.jsonl").read_text().splitlines()]
    assert records[0]["action"]["kind"] == "return_to_main_menu"
    assert records[0]["memory_snapshot_id"] is None
    assert store.load("run_unknown", "v0.111.0") is None
    db.close()
    store.close()
