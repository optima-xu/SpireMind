"""Regression checks for verified live failures; all model transport is offline."""

import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from spiremind.config import ModelConfig
from spiremind.context.action_facts import action_evaluations
from spiremind.context.compiler import AgentContext
from spiremind.context.views import progress_view
from spiremind.core.actions import Action
from spiremind.core.enums import ActionKind, Scene
from spiremind.core.state import Card, CombatState, Enemy, GameState, Intent, Power, PublicFacts, RunState
from spiremind.knowledge.library import StrategyLibrary
from spiremind.memory.async_store import AsyncMemory
from spiremind.memory.evidence_io import import_evidence
from spiremind.memory.experience import ExperienceStore, digest, import_history
from spiremind.memory.manager import MemoryContext
from spiremind.memory.storage_sqlite import MemoryStore
from spiremind.providers.calculator import execute_calculator
from spiremind.providers.openai import OpenAIProvider, ProviderError
from spiremind.providers.protocols import RequestBudget
from spiremind.runtime.control import RunControl, control_status
from spiremind.runtime.locking import SingleWriter
from spiremind.runtime.trace import TraceWriter
from spiremind.strategies.combat import CombatStrategy
from spiremind.strategies.combat_tactics import assess, visible_offense_plan
from spiremind.strategies.fallback import conservative_choice
from spiremind.strategies.tactics.setup import free_rage_action


@pytest.fixture
def live_cases():
    data = json.loads(
        (Path(__file__).parent / "fixtures/v0.111.0-live-robustness.json").read_text(encoding="utf-8")
    )
    return {item["case"]: GameState.model_validate(item["state"]) for item in data}


def numeric_state(*, hp=10, energy=1, block=10, powers=(), enemy_hp=15):
    body = Card(
        id="body_slam",
        ref="body",
        type="attack",
        cost=0,
        values=PublicFacts.of({"CalculationBase": 0, "ExtraDamage": 1, "CalculatedDamage": block}),
    )
    defend = Card(id="defend", ref="defend", type="skill", cost=1, values=PublicFacts.of({"Block": 5}))
    enemy = Enemy(
        id="enemy",
        ref="enemy",
        hp=enemy_hp,
        max_hp=enemy_hp,
        intents=(Intent(type="Attack", damage=24, hits=1),),
    )
    return GameState(
        game_version="v0.111.0",
        decision_id="d",
        revision=1,
        scene=Scene.COMBAT,
        run=RunState(id="seed", character="ironclad", hp=hp, max_hp=80),
        combat=CombatState(
            turn=1, block=block, energy=energy, hand=(body, defend), enemies=(enemy,), powers=powers
        ),
        legal_actions=(
            Action(id="body", decision_id="d", kind=ActionKind.PLAY_CARD, card_id="body", target_id="enemy"),
            Action(id="defend", decision_id="d", kind=ActionKind.PLAY_CARD, card_id="defend"),
            Action(id="end", decision_id="d", kind=ActionKind.END_TURN),
        ),
    )


def test_body_slam_search_recomputes_damage_after_block_but_not_after_end_turn_plating():
    state = numeric_state(powers=(Power(id="plating_power", amount=4),))
    facts = assess(state)
    assert facts["evaluated_actions"][0]["hp_damage"] == 10
    assert facts["end_turn_block_gain"] == 4
    assert facts["verified_lethal_plan"] == ["defend", "body"]
    assert visible_offense_plan(state)["max_damage"] == 15


def test_body_slam_formula_mismatch_abstains_instead_of_using_metadata_as_bonuses():
    state = numeric_state()
    body = state.combat.hand[0].model_copy(
        update={"values": PublicFacts.of({"CalculationBase": 0, "ExtraDamage": 1, "CalculatedDamage": 999})}
    )
    state = state.model_copy(
        update={"combat": state.combat.model_copy(update={"hand": (body, state.combat.hand[1])})}
    )
    assert visible_offense_plan(state)["complete"] is False


def test_pyre_does_not_give_extra_current_turn_energy_and_plating_is_version_bound():
    state = numeric_state(energy=0, powers=(Power(id="pyre_power", amount=2),))
    state = state.model_copy(update={"legal_actions": (state.legal_actions[0], state.legal_actions[-1])})
    assert visible_offense_plan(state)["max_damage"] == 10
    unknown = numeric_state(powers=(Power(id="plating_power", amount=4),)).model_copy(
        update={"game_version": "v0.999.0"}
    )
    assert "plating_power" in assess(unknown)["unmodeled_player_powers"]
    assert assess(unknown)["end_turn_block_gain"] == 0


async def test_actual_rage_ordering_is_fixed_without_claiming_surrounded_combat_is_solved(live_cases):
    state = live_cases["revision_209"]
    decision = await CombatStrategy(None, None, None).decide(state, None)
    card = next(c for c in state.combat.hand if c.ref == decision.action.card_id)
    assert card.id == "rage" and card.cost == 0
    assert decision.policy_rule == "play_free_rage_before_attack"
    assert assess(state)["survival_status"] == "unknown"
    capped = state.model_copy(
        update={
            "combat": state.combat.model_copy(
                update={"powers": state.combat.powers + (Power(id="ringing_power", amount=1),)}
            )
        }
    )
    assert free_rage_action(capped) is None
    reactive = state.model_copy(
        update={
            "combat": state.combat.model_copy(
                update={"powers": state.combat.powers + (Power(id="unknown_retaliation", amount=1),)}
            )
        }
    )
    assert free_rage_action(reactive) is None


def test_unmovable_counter_remains_unknown_even_when_next_card_preview_is_doubled(live_cases):
    for case in ("revision_36", "revision_37"):
        facts = assess(live_cases[case])
        assert "unmovable_power" in facts["unmodeled_player_powers"]
        assert facts["survival_search"]["optimal"] is False
        assert not facts["verified_lethal_plan"]


@pytest.mark.parametrize(
    "case,card_id,field,value",
    [
        ("revision_200", "taunt", "live_block", 10),
        ("revision_202", "defend_ironclad", "live_block", 8),
        ("revision_203", "strike_ironclad", "target_damage_per_hit", 19),
        ("revision_209", "twin_strike", "live_damage_per_hit", 15),
        ("revision_209", "twin_strike", "target_damage_per_hit", 22),
        ("revision_217", "body_slam", "live_damage_per_hit", 28),
    ],
)
def test_grounded_calculator_uses_live_owner_previews_without_readding_bonuses(
    live_cases, case, card_id, field, value
):
    state = live_cases[case]
    card = next(c for c in state.combat.hand if c.id == card_id)
    action = next(a for a in state.legal_actions if a.card_id == card.ref)
    evaluations = action_evaluations(state, assess(state))
    result = execute_calculator(json.dumps({"action_ids": [action.id]}), evaluations)
    facts = json.loads(result[0]["result"])
    assert facts["forecast"][field] == value
    assert (facts["revision"], facts["decision_id"]) == (state.revision, state.decision_id)
    assert execute_calculator('{"action_ids":["stale-action"]}', evaluations) == [
        {"error": "unknown_current_action"}
    ]


@pytest.fixture
def provider_settings(monkeypatch):
    monkeypatch.setenv("ROBUSTNESS_TEST_KEY", "test-key")
    return ModelConfig(model="test", api_key_env="ROBUSTNESS_TEST_KEY", attempts=2, max_tokens=128)


def wire_answer(choice):
    return {
        "model": "test",
        "choices": [{"message": {"content": json.dumps(choice)}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 5},
    }


async def test_bad_numeric_forecast_is_repaired_once_using_bound_tool_results(provider_settings, monkeypatch):
    async def no_sleep(_):
        pass

    monkeypatch.setattr("spiremind.providers.openai.asyncio.sleep", no_sleep)
    facts = (
        {
            "action_id": "A",
            "revision": 5,
            "decision_id": "d",
            "forecast": {"live_block": 8},
            "effects_complete": True,
        },
    )
    context = AgentContext("x", "Choose", "Use current facts", 20, (), (), facts)
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) == 1:
            data = wire_answer({})
            data["choices"][0] = {
                "finish_reason": "tool_calls",
                "message": {
                    "tool_calls": [
                        {
                            "id": "calc",
                            "type": "function",
                            "function": {"name": "calculate", "arguments": '{"action_ids":["A"]}'},
                        }
                    ]
                },
            }
            return httpx.Response(200, json=data)
        if len(calls) == 3:
            assert body["tool_choice"] == "auto"
            assert sum(m["role"] == "tool" for m in body["messages"]) == 1
        value = 11 if len(calls) == 2 else 8
        return httpx.Response(
            200,
            json=wire_answer(
                {
                    "action_id": "A",
                    "reason": "Current Block preview",
                    "confidence": 0.9,
                    "forecast": {"live_block": value},
                }
            ),
        )

    provider = OpenAIProvider(provider_settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = await provider.choose(context, {"A"})
    assert result.choice.forecast == {"live_block": 8}
    assert provider.calculator_calls == provider.invalid_responses == 1
    assert provider.calls == 3
    await provider.close()


@pytest.mark.parametrize("status", [403, 429])
async def test_http_rejection_is_not_recorded_as_fabricated_billed_tokens(provider_settings, status):
    settings = provider_settings.model_copy(update={"attempts": 1})
    budget = RequestBudget(2, 10000)
    provider = OpenAIProvider(
        settings,
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: httpx.Response(status, text="private body"))
        ),
        budget,
    )
    with pytest.raises(ProviderError):
        await provider.choose(AgentContext("x", "Choose", "A", 20, (), ()), {"A"})
    assert budget.requests == 1 and budget.tokens == 0
    assert provider.input_tokens == provider.output_tokens == 0
    assert provider.request_records[0]["http_status"] == status
    assert provider.request_records[0]["usage_estimated"] is False
    await provider.close()


async def test_transport_failure_remains_conservatively_budgeted(provider_settings):
    def fail(request):
        raise httpx.ReadTimeout("private transport details", request=request)

    settings = provider_settings.model_copy(update={"attempts": 1})
    provider = OpenAIProvider(
        settings, httpx.AsyncClient(transport=httpx.MockTransport(fail)), RequestBudget(2, 10000)
    )
    with pytest.raises(ProviderError):
        await provider.choose(AgentContext("x", "Choose", "A", 20, (), ()), {"A"})
    assert provider.input_tokens + provider.output_tokens > 0
    assert provider.reported_input_tokens + provider.reported_output_tokens == 0
    assert provider.request_records[0]["usage_estimated"] is True
    await provider.close()


def test_online_episodes_respect_frozen_holdout_and_cannot_disable_training_lessons(states, tmp_path):
    from test_learning_pipeline import evidence, proposal

    memory = MemoryStore(tmp_path / "memory.sqlite")
    store = ExperienceStore(memory.db)
    items = [evidence(store, states[4], seed) for seed in ("seed1", "seed2", "seed3")]
    p = proposal(items[0])
    p.evidence_ids = [e["id"] for e in items]
    store.propose(p)
    with store.db:
        store.set_history_split({"train": ["seed1", "seed2", "seed3"], "holdout": ["held"]})
    held = evidence(store, states[4], "held", block=999)
    store.check_contradictions(held)
    assert store.compact(held["id"])["partition"] == "holdout"
    assert store.inspect()["lessons"] == {"active": 1}
    with store.db:
        store.set_history_split({"train": ["held"], "holdout": []})
    assert "held" in store.history_split["holdout"]
    memory.close()


def test_tactical_learning_requires_independent_seeds_and_rechecks_current_preconditions(
    live_cases, tmp_path
):
    state = live_cases["revision_209"]
    memory = MemoryStore(tmp_path / "memory.sqlite")
    store = ExperienceStore(memory.db)
    action = free_rage_action(state)
    for i in range(3):
        new = state.model_copy(
            update={
                "decision_id": "after:" + str(i),
                "revision": state.revision + 1,
                "combat": state.combat.model_copy(
                    update={
                        "powers": tuple(
                            p.model_copy(update={"amount": (p.amount or 0) + 5})
                            if p.id == "rage_power"
                            else p
                            for p in state.combat.powers
                        )
                    }
                ),
            }
        )
        episode = store.episode(state, action, new, "combat", "combat", True, "seed" + str(i))
        store.insert(episode)
        store.consolidate()
        expected = "active" if i == 2 else "candidate"
        assert store.inspect()["tactical_lessons"] == {expected: 1}
    skills = store.retrieve(state, "combat")["skills"]
    assert skills and "before attacks" in skills[0]["instruction"]
    assert not store.retrieve(state, "map")["skills"]
    capped = state.model_copy(
        update={
            "combat": state.combat.model_copy(
                update={"powers": state.combat.powers + (Power(id="ringing_power", amount=1),)}
            )
        }
    )
    assert not store.retrieve(capped, "combat")["skills"]
    # The same local preconditions with a verified adverse result retire the tactic.
    bad_after = new.model_copy(
        update={"decision_id": "bad", "run": state.run.model_copy(update={"hp": state.run.hp - 1})}
    )
    counterexample = store.episode(state, action, bad_after, "combat", "combat", True, "counterexample")
    store.insert(counterexample)
    store.check_contradictions(counterexample)
    assert store.inspect()["tactical_lessons"] == {"disabled": 1}
    assert store.retrieve(state, "combat")["warnings"][0]["tactic"] == "rage_before_attack"
    memory.close()


async def test_learned_tactic_is_used_and_a_counterexample_prevents_automatic_forcing(live_cases):
    state = live_cases["revision_209"]
    memory = MemoryContext(
        snapshot_id="snapshot",
        run={},
        working={},
        skills=(),
        experiences={"skills": [{"tactic": "rage_before_attack"}]},
    )
    strategy = CombatStrategy(None, None, conservative_choice)
    assert (await strategy.decide(state, memory)).policy_rule == "learned_rage_before_attack"
    memory = replace(
        memory, experiences={"warnings": [{"tactic": "rage_before_attack", "status": "disabled"}]}
    )
    assert (await strategy.decide(state, memory)).policy_rule not in {
        "learned_rage_before_attack",
        "play_free_rage_before_attack",
    }


def test_progress_cache_keeps_unknown_metrics_and_returns_independent_data():
    power = Power(
        id="unknown",
        amount=1,
        trigger_progress=PublicFacts.of(
            {
                "progress_known": False,
                "counters": {"amount": 1},
                "parameters": {"Limit": 4},
                "metrics": [
                    {"name": "amount", "value": 1, "source_member": "Amount"},
                    {"name": "opaque_counter", "value": 7, "source_member": "Unknown"},
                ],
                "note": "Repeated exporter metadata",
            }
        ),
    )
    first = progress_view(power)
    first["trigger_progress"]["parameters"]["Limit"] = 999
    second = progress_view(power)["trigger_progress"]
    assert second["parameters"]["Limit"] == 4
    assert second["progress_known"] is False
    assert second["metrics"] == [{"name": "opaque_counter", "value": 7}]


def test_interrupted_history_import_uses_only_verified_receipts(live_cases, tmp_path):
    state = live_cases["revision_209"]
    action = free_rage_action(state)
    new = state.model_copy(update={"decision_id": "next", "revision": 210})
    root = tmp_path / "traces"
    folder = root / "unfinished"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text('{"mode":"live"}', encoding="utf-8")
    (folder / "states.jsonl").write_text(
        state.model_dump_json() + "\n" + new.model_dump_json(), encoding="utf-8"
    )
    row = {
        "decision_id": state.decision_id,
        "state_revision": state.revision,
        "strategy_name": "combat",
        "action": action.model_dump(mode="json"),
        "verify_ok": False,
        "semantic_success": False,
        "execution_result": {
            "status": "completed",
            "action_id": action.id,
            "previous_decision_id": state.decision_id,
            "next_decision_id": new.decision_id,
        },
    }
    (folder / "decisions.jsonl").write_text(json.dumps(row) + '\n{"truncated":', encoding="utf-8")
    (folder / "reconciliations.jsonl").write_text(
        json.dumps(row | {"verify_ok": True, "semantic_success": True}), encoding="utf-8"
    )
    memory = MemoryStore(tmp_path / "memory.sqlite")
    store = ExperienceStore(memory.db)
    result = import_history(store, root)
    assert result["traces"] == result["incomplete_traces"] == 1
    assert result["malformed"] == 1 and result["inserted"] == 1
    assert memory.db.execute("SELECT verified FROM episodes").fetchone()[0] == 1
    lineage = digest((state.game_version, state.run.character, state.run.id))
    assert lineage in store.history_split["train"]
    assert import_history(store, root)["inserted"] == 0
    memory.close()


async def test_bootstrap_caches_an_unchanged_dataset_across_storage_restarts(tmp_path):
    root = tmp_path / "traces"
    root.mkdir()
    worker = await AsyncMemory.create(tmp_path / "m.sqlite", tmp_path / "c.sqlite", StrategyLibrary())
    first = await worker.bootstrap(root)
    assert first["cached"] is False and first["history"]["traces"] == 0
    assert (await worker.bootstrap(root))["cached"] is True
    await worker.close()
    worker = await AsyncMemory.create(tmp_path / "m.sqlite", tmp_path / "c.sqlite", StrategyLibrary())
    try:
        assert (await worker.bootstrap(root))["cached"] is True
    finally:
        await worker.close()


def test_failed_evidence_import_rolls_back_cached_and_persistent_partitions(tmp_path):
    import sqlite3
    from importlib.resources import files

    data = json.loads(
        files("spiremind").joinpath("knowledge/benchmarks/training_evidence.json").read_text(encoding="utf-8")
    )
    data["episodes"] = data["episodes"][:1]
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    memory = MemoryStore(tmp_path / "memory.sqlite")
    store = ExperienceStore(memory.db)
    memory.db.executescript(
        "CREATE TRIGGER fail_import BEFORE INSERT ON episodes BEGIN SELECT RAISE(ABORT,'injected'); END;"
    )
    with pytest.raises(sqlite3.IntegrityError):
        import_evidence(store, path)
    assert store.history_split == {"train": [], "holdout": []}
    assert memory.db.execute("SELECT payload FROM memory_meta WHERE key='history_split'").fetchone() is None
    assert memory.db.execute("SELECT COUNT(*) FROM episodes").fetchone()[0] == 0
    memory.close()


def test_status_shows_current_phase_without_exposing_arbitrary_trace_fields(tmp_path):
    trace = TraceWriter(tmp_path, "test")
    trace.write_json(
        "progress.json",
        {"phase": "model", "steps": 5, "provider_failure_seconds": 0, "private_field": "not public status"},
    )
    control_path, lock = tmp_path / "control.json", tmp_path / "writer.lock"
    with SingleWriter(lock), RunControl(control_path, {"attempt_id": trace.attempt_id}):
        status = control_status(control_path, lock)
    assert status["active"] and status["progress"]["phase"] == "model"
    assert "private_field" not in status["progress"]


def test_atomic_trace_replacement_recovers_a_transient_windows_sharing_failure(tmp_path, monkeypatch):
    from spiremind.core import files

    original = Path.replace
    calls = []

    def temporarily_denied(path, target):
        calls.append(target)
        if len(calls) <= 2:
            raise PermissionError("file briefly held by reader")
        return original(path, target)

    monkeypatch.setattr(Path, "replace", temporarily_denied)
    monkeypatch.setattr(files.time, "sleep", lambda _: None)
    trace = TraceWriter(tmp_path, "test")
    assert len(calls) == 3
    assert (trace.path / "manifest.json").exists()
