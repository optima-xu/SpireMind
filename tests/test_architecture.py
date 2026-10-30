import ast
import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from spiremind.adapters.control import RunControl, control_status
from spiremind.adapters.locking import SingleWriter
from spiremind.adapters.model.openai import OpenAIProvider
from spiremind.adapters.storage.execution import ExecutionJournal
from spiremind.adapters.storage.memory import MemoryStore
from spiremind.adapters.telemetry.trace import TraceWriter
from spiremind.application.run_state import MemoryManager
from spiremind.application.session import AgentRuntime
from spiremind.config import Config
from spiremind.core.actions import Action
from spiremind.core.context import AgentContext, MemoryContext
from spiremind.core.decision import Decision, StrategyUpdate
from spiremind.core.enums import ActionKind, Scene
from spiremind.core.ports import EnvironmentError
from spiremind.core.state import Card, GameState, Power, PublicFacts
from spiremind.core.transitions import verify_transition
from spiremind.decision.deck import DeckAnalyzer
from spiremind.decision.frame import DecisionFrame
from spiremind.decision.mechanics.effects import attack_profile, parsed_scope
from spiremind.decision.mechanics.verification import verify_effect
from spiremind.decision.policies.fallback import conservative_choice
from spiremind.decision.router import SceneRouter
from spiremind.evaluation.mock import MockEnvironment, demo_states
from spiremind.evaluation.quality import DEFAULT_CASES, evaluate
from spiremind.knowledge.library import StrategyLibrary
from spiremind.learning.experience import ExperienceStore


def quality_state(identity):
    cases = json.loads(DEFAULT_CASES.read_text(encoding="utf-8"))["cases"]
    return GameState.model_validate(next(case["state"] for case in cases if case["id"] == identity))


def test_import_boundaries_are_enforced():
    root = Path(__file__).parents[1] / "src" / "spiremind"
    for layer in ("core", "decision", "learning"):
        for path in (root / layer).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            modules = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    modules.append(node.module or "")
                elif isinstance(node, ast.Import):
                    modules.extend(item.name for item in node.names)
            forbidden = ("spiremind.application", "spiremind.adapters", "spiremind.bootstrap")
            if layer == "core":
                forbidden += ("spiremind.decision", "spiremind.learning", "spiremind.knowledge")
            assert not any(module.startswith(forbidden) for module in modules), path


async def test_labeled_quality_suite():
    report = await evaluate()
    assert report["model_calls"] == 0
    assert report["passed"] == report["total"] >= 8, report["cases"]


@pytest.mark.parametrize("source", ["model", "rule", "fallback"])
def test_final_gate_rejects_a_policy_that_ignores_filtered_actions(source):
    state = quality_state("hp_cost_cannot_be_paid")
    frame = DecisionFrame.prepare(state, MemoryContext("test", {}, {}, ()))
    assert [action.id for action in frame.policy_state.legal_actions] == ["end"]
    choice = Decision(
        action=state.legal_actions[0],
        reason=source,
        fallback=source == "fallback",
        policy_rule="bad_rule" if source == "rule" else None,
    )
    with pytest.raises(ValueError, match="visible_hp_cost"):
        frame.validate(choice)


def test_transition_rejects_an_unrelated_run_and_game_version(states):
    before, after = states[2:4]
    assert verify_transition(before, before.legal_actions[0], after)
    other = after.model_copy(update={"run": after.run.model_copy(update={"id": "other-seed"})})
    assert not verify_transition(before, before.legal_actions[0], other)
    assert not verify_transition(
        before, before.legal_actions[0], after.model_copy(update={"game_version": "v9"})
    )


def test_effect_verification_is_distinct_from_a_valid_transition():
    before = quality_state("block_prevents_death")
    action = before.legal_actions[0]
    after = before.model_copy(
        update={
            "decision_id": "next",
            "revision": 2,
            "combat": before.combat.model_copy(update={"energy": 0, "block": 5, "hand": ()}),
        }
    )
    assert verify_transition(before, action, after)
    assert verify_effect(before, action, after).status == "confirmed"
    wrong = after.model_copy(update={"combat": after.combat.model_copy(update={"block": 0})})
    assert verify_transition(before, action, wrong)
    assert verify_effect(before, action, wrong).status == "conflict"


def test_target_preview_does_not_mutate_another_target():
    state = quality_state("focus_attacking_enemy")
    card = state.combat.hand[0].model_copy(update={"target_values": PublicFacts.of({"0": {"Repeat": 2}})})
    with parsed_scope():
        assert attack_profile(card, 0)["hits"] == 2
        assert attack_profile(card, 1)["hits"] == 1


def test_memory_rollback_and_retry_publish_exactly_once(tmp_path, states):
    store = MemoryStore(tmp_path / "memory.sqlite")
    manager = MemoryManager(store)
    before, after = states[6:8]
    context = manager.context(before, "run")
    old_run = manager.run.model_dump()
    old_working = manager.working.model_dump()
    store.db.execute(
        "CREATE TRIGGER fail_audit BEFORE INSERT ON memory_audit BEGIN SELECT RAISE(ABORT, 'injected'); END"
    )
    proposal = StrategyUpdate(gold_policy="Reserve 100 for removal", current_goal="Reach the next rest")
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        manager.update_sync(before, before.legal_actions[0], after, proposal)
    assert manager.run.model_dump() == old_run
    assert manager.working.model_dump() == old_working
    assert store.load(before.run.id, before.game_version).model_dump() == old_run
    assert store.db.execute("SELECT count(*) FROM committed_transitions").fetchone()[0] == 0
    store.db.execute("DROP TRIGGER fail_audit")
    first = manager.update_sync(before, before.legal_actions[0], after, proposal)
    second = manager.update_sync(
        before,
        before.legal_actions[0],
        after,
        proposal,
        expected_instance_id=context.instance_id,
    )
    assert first == second
    assert manager.run.policy_version == 1
    assert store.db.execute("SELECT count(*) FROM memory_audit").fetchone()[0] == 1
    assert store.db.execute("SELECT count(*) FROM committed_transitions").fetchone()[0] == 1
    store.close()


@pytest.mark.parametrize("payload", ["null", "[]", "{}", '{"schema":9}'])
def test_corrupt_execution_record_cannot_enable_a_new_action(tmp_path, payload):
    journal = ExecutionJournal(tmp_path / "execution.json")
    journal.path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid pending execution"):
        journal.load()
    assert journal.path.exists()


def test_restarted_embark_keeps_the_committed_run_instance(tmp_path, states):
    path = tmp_path / "memory.sqlite"
    store = MemoryStore(path)
    manager = MemoryManager(store)
    manager.begin_run(states[2], transition_id="embark-receipt")
    instance = manager.run.instance_id
    store.close()
    store = MemoryStore(path)
    restarted = MemoryManager(store)
    restarted.begin_run(states[2], transition_id="embark-receipt")
    assert restarted.run.instance_id == instance
    assert store.db.execute("SELECT count(*) FROM committed_transitions").fetchone()[0] == 1
    store.close()


async def test_restart_reconciles_without_requesting_or_sending_another_action(tmp_path):
    class InterruptedBridge(MockEnvironment):
        interrupted = False

        async def execute(self, action):
            receipt = await super().execute(action)
            self.interrupted = True
            return receipt

        async def observe(self):
            if self.interrupted:
                self.interrupted = False
                raise EnvironmentError("connection lost after acceptance")
            return await super().observe()

    class Policy:
        name = "event"
        last_context = None
        calls = 0

        async def decide(self, state, memory):
            self.calls += 1
            return conservative_choice(state, memory)

    bridge, policy = InterruptedBridge(demo_states()[2:]), Policy()
    journal = ExecutionJournal(tmp_path / "execution.json")

    def runtime(store):
        return AgentRuntime(
            bridge,
            MemoryManager(store),
            SceneRouter(policy, policy, policy, policy),
            DeckAnalyzer(StrategyLibrary()),
            TraceWriter(tmp_path / "runs", "restart"),
            Config(),
            journal=journal,
        )

    store = MemoryStore(tmp_path / "memory.sqlite")
    with pytest.raises(EnvironmentError):
        await runtime(store).step()
    assert journal.load()["receipt"]["status"] == "completed"
    store.close()
    restarted_store = MemoryStore(tmp_path / "memory.sqlite")
    restarted = runtime(restarted_store)
    await restarted.step()
    assert len(bridge.executed) == policy.calls == restarted.verified == 1
    assert journal.load() is None
    assert restarted_store.db.execute("SELECT count(*) FROM committed_transitions").fetchone()[0] == 1
    restarted_store.close()


def test_status_reads_trace_outside_the_lock_directory(tmp_path):
    attempt = "20261030T120000-abcdef12"
    trace_dir = tmp_path / "runs" / attempt
    trace_dir.mkdir(parents=True)
    (trace_dir / "progress.json").write_text('{"phase":"verify","steps":7}', encoding="utf-8")
    lock = tmp_path / "locks" / "writer.lock"
    path = lock.with_suffix(".control.json")
    with SingleWriter(lock), RunControl(path, {"attempt_id": attempt, "trace_dir": str(trace_dir)}):
        assert control_status(path, lock)["progress"] == {"phase": "verify", "steps": 7}


def test_incremental_learning_rechecks_dynamic_values_and_legal_actions(tmp_path):
    state = quality_state("take_visible_lethal")
    rage = Card(id="rage", ref="rage", type="skill", cost=0, values=PublicFacts.of({"Power": 5}))
    action = Action(id="rage", decision_id=state.decision_id, kind=ActionKind.PLAY_CARD, card_id="rage")
    state = state.model_copy(
        update={
            "combat": state.combat.model_copy(update={"hand": (*state.combat.hand, rage)}),
            "legal_actions": (*state.legal_actions, action),
        }
    )
    store = MemoryStore(tmp_path / "memory.sqlite")
    experience = ExperienceStore(store.db)
    for i in range(3):
        after = state.model_copy(
            update={
                "decision_id": f"next-{i}",
                "revision": 2,
                "combat": state.combat.model_copy(update={"powers": (Power(id="rage_power", amount=5),)}),
            }
        )
        episode = experience.episode(state, action, after, "combat", "combat", True, f"seed-{i}")
        experience.insert(episode)
    experience.enqueue("seed-2")
    experience.consolidate([episode["id"]])
    assert experience.inspect()["reflection_jobs"] == {"pending": 1}
    assert experience.retrieve(state, "combat")["skills"]
    changed = state.model_copy(
        update={
            "combat": state.combat.model_copy(
                update={
                    "hand": (
                        state.combat.hand[0],
                        rage.model_copy(update={"values": PublicFacts.of({"Power": 1})}),
                    ),
                }
            ),
        }
    )
    assert not experience.retrieve(changed, "combat")["skills"]
    no_attack = state.model_copy(update={"legal_actions": (action, state.legal_actions[1])})
    assert not experience.retrieve(no_attack, "combat")["skills"]
    assert experience.retrieve(state, "combat")["skills"]
    store.close()


async def test_combat_feedback_informs_the_next_run_intent(tmp_path):
    state = quality_state("block_prevents_death")
    after = state.model_copy(
        update={
            "scene": Scene.CARD_REWARD,
            "combat": None,
            "revision": 2,
            "decision_id": "reward",
            "legal_actions": (),
            "run": state.run.model_copy(update={"hp": 3}),
        }
    )
    store = MemoryStore(tmp_path / "memory.sqlite")
    manager = MemoryManager(store)
    manager.context(state, "combat")
    manager.update_sync(state, state.legal_actions[0], after, producer="combat")
    manager.apply_analysis(after, DeckAnalyzer(StrategyLibrary()).analyze(after))
    context = manager.context(after, "run")
    assert context.run["combat_feedback"][0]["hp_lost"] == 1
    assert context.run["combat_feedback"][0]["ended"] is True
    assert context.run["intent"]["priorities"][0] == "immediate_survival"
    assert "observed_hp_loss_last_1_combats=1" in context.run["intent"]["evidence"]
    await manager.finish_run("death")
    assert store.scopes(manager.run.instance_id) == {}
    store.close()


async def test_deepseek_configuration_uses_only_the_new_key(monkeypatch):
    config = Config.load(Path(__file__).parents[1] / "config.example.toml")
    assert Config().model.extra_body == config.model.extra_body == {"thinking": {"type": "disabled"}}
    monkeypatch.setenv("deepseek_api_key", "new-offline-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "old-key-must-not-be-used")
    seen = []

    def handler(request):
        assert request.url.host == "api.deepseek.com"
        assert request.headers["authorization"] == "Bearer new-offline-key"
        body = json.loads(request.content)
        assert body["model"] == "deepseek-flash"
        assert body["thinking"] == {"type": "disabled"}
        seen.append(body)
        return httpx.Response(
            200,
            json={
                "model": "deepseek-flash",
                "choices": [
                    {
                        "message": {"content": '{"action_id":"ok","reason":"offline","confidence":1}'},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAIProvider(config.model.model_copy(update={"calculator_mode": "off"}), client)
    try:
        await provider.choose(AgentContext("test", "Choose JSON", "ok", 5, (), ()), {"ok"})
        assert len(seen) == 1
    finally:
        await provider.close()
