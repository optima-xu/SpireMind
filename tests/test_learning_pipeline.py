import asyncio
import json
import sqlite3
import threading
import time

import httpx
import pytest

from spiremind.config import ModelConfig
from spiremind.context.compiler import AgentContext
from spiremind.core.decision import StrategyUpdate
from spiremind.core.enums import Scene
from spiremind.core.state import PublicFacts
from spiremind.knowledge.cards import CardDB, CardFact
from spiremind.knowledge.library import StrategyLibrary
from spiremind.memory.async_store import AsyncMemory
from spiremind.memory.evidence_io import import_evidence
from spiremind.memory.experience import ExperienceStore, LessonProposal
from spiremind.memory.manager import MemoryManager
from spiremind.memory.reflection import ReflectionAgent
from spiremind.memory.storage_sqlite import MemoryStore
from spiremind.providers.openai import OpenAIProvider, retry_after_seconds
from spiremind.providers.protocols import BudgetExceeded, RequestBudget
from spiremind.runtime.async_trace import AsyncTraceWriter, TraceWriteError
from spiremind.strategies.run import DeckAnalyzer


async def test_private_scopes_resume_and_same_seed_instance(states, tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite")
    manager = MemoryManager(store)
    combat = states[4]
    original = await manager.context_for(combat, "combat")
    manager.working.current_goal = "combat private goal"
    await manager.context_for(combat, "combat")
    run = await manager.context_for(states[5], "run")
    assert run.working["current_goal"] == ""
    restored = MemoryManager(store)
    context = await restored.context_for(combat, "combat")
    assert context.instance_id == original.instance_id
    assert context.working["current_goal"] == "combat private goal"
    selection = combat.model_copy(update={"scene": Scene.CARD_SELECTION})
    assert (await restored.context_for(selection, "combat")).working["current_goal"] == "combat private goal"
    await restored.finish_run("death")
    fresh = await restored.context_for(combat, "combat")
    assert fresh.instance_id != original.instance_id
    assert fresh.working["current_goal"] == ""
    store.close()


async def test_ownership_cas_and_handoff_invalidation(states, tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite")
    manager = MemoryManager(store)
    shop = states[6].model_copy(update={"run": states[6].run.model_copy(update={"boss": "boss"})})
    context = await manager.context_for(shop, "run")
    second_manager = MemoryManager(store)
    old_context = await second_manager.context_for(shop, "run")
    audit = await manager.update(
        shop,
        shop.legal_actions[0],
        shop,
        StrategyUpdate(gold_policy="Save 100", route_preferences=["elite"]),
        producer="run",
        expected_policy_version=context.policy_version,
    )
    assert audit["applied"] == {"gold_policy": "Save 100"}
    assert audit["rejected"] == {"route_preferences": "field_owned_by_map"}
    stale = await manager.update(
        shop,
        shop.legal_actions[0],
        shop,
        StrategyUpdate(gold_policy="Spend all"),
        producer="run",
        expected_policy_version=context.policy_version,
    )
    assert stale["applied"] == {}
    assert manager.run.gold_policy == "Save 100"
    second_audit = await second_manager.update(
        shop,
        shop.legal_actions[0],
        shop,
        StrategyUpdate(gold_policy="Old agent overwrites"),
        producer="run",
        expected_policy_version=old_context.policy_version,
    )
    assert second_audit["applied"] == {}
    assert store.load(shop.run.id, shop.game_version).gold_policy == "Save 100"
    combat = states[4]
    await manager.update(shop, shop.legal_actions[0], combat, producer="run")
    packet = (await manager.context_for(combat, "combat")).handoff
    assert packet["producer"] == "run"
    assert "HP" in packet["summary"] and "action_id" not in packet
    changed = combat.model_copy(update={"run": combat.run.model_copy(update={"hp": combat.run.hp - 1})})
    assert (await manager.context_for(changed, "combat")).handoff is None
    store.close()


def test_combined_transaction_rolls_back_without_poisoning_caches(tmp_path):
    from spiremind.memory.run import RunMemory

    store = MemoryStore(tmp_path / "memory.sqlite")
    run = RunMemory(run_id="seed", game_version="v")

    def fail():
        raise RuntimeError("injected")

    with pytest.raises(RuntimeError):
        store.save_context(run, {"test": 1}, evidence=fail)
    assert store.load("seed", "v") is None
    assert not store._snapshot_ids and not store._persisted_payloads
    assert store.transactions == 0
    snapshot = store.save_context(run, {"test": 1})
    assert store.load_snapshot(snapshot) == {"test": 1}
    assert store.transactions == 1
    store.close()


def test_bounded_card_cache_negative_entries_upgrade_and_invalidation(tmp_path):
    cards = CardDB(tmp_path / "cards.sqlite")
    fact = CardFact(card_id="defend", game_version="v", source_version="a", text="5 Block")
    cards.put(fact)
    assert cards.lookup({"defend", "missing"}, "v") == [fact]
    assert cards.lookup({"defend", "missing"}, "v") == [fact]
    assert cards.lookup_queries == 1
    assert cards.lookup({("defend", True)}, "v") == []
    cards.put(fact.model_copy(update={"text": "6 Block"}))
    assert cards.lookup({"defend"}, "v")[0].text == "6 Block"
    for number in range(1100):
        cards.lookup({f"unknown{number}"}, "v")
    assert cards.cache.stats()["size"] == 1024
    cards.close()


def test_deck_cache_keeps_zero_hp_live(states):
    analyzer = DeckAnalyzer(StrategyLibrary())
    normal = analyzer.analyze(states[4])
    dead = states[4].model_copy(update={"run": states[4].run.model_copy(update={"hp": 0})})
    assert analyzer.analyze(dead)["elite_readiness"] == 0
    assert analyzer.cache.hits == 1
    normal["needs"]["block"] = -1
    assert analyzer.analyze(states[4])["needs"]["block"] >= 0
    facts = PublicFacts.of({"nested": {"number": 5}})
    facts.unpack()["nested"]["number"] = 9
    assert facts.unpack()["nested"]["number"] == 5


def evidence(store, state, lineage, block=5, partition="train"):
    action = next(a for a in state.legal_actions if a.card_id == "c1")
    after = state.model_copy(
        update={
            "decision_id": lineage + "-next",
            "revision": state.revision + 1,
            "combat": state.combat.model_copy(update={"block": state.combat.block + block}),
        }
    )
    item = store.episode(state, action, after, "combat", "combat", True, lineage)
    store.insert(item, partition)
    return item


def proposal(item):
    return LessonProposal(
        owner="combat",
        game_version=item["before"]["game_version"],
        character="ironclad",
        scene="combat",
        conditions=item["conditions"],
        metric="block_delta",
        value=5,
        evidence_ids=[item["id"]],
        instruction="Block observed",
    )


def test_learned_promotion_contradiction_and_holdout_exclusion(states, tmp_path):
    memory = MemoryStore(tmp_path / "memory.sqlite")
    store = ExperienceStore(memory.db)
    first = evidence(store, states[4], "seed1")
    p = proposal(first)
    assert store.propose(p)["status"] == "candidate"
    repeated = evidence(store, states[4], "seed1", partition="train")
    assert repeated["id"] == first["id"]
    other = evidence(store, states[4], "seed2")
    held = evidence(store, states[4], "seed-held", partition="holdout")
    p.evidence_ids = [first["id"], other["id"], held["id"]]
    with pytest.raises(ValueError, match="not_supported"):
        store.propose(p)
    third = evidence(store, states[4], "seed3")
    p.evidence_ids = [first["id"], other["id"], third["id"]]
    assert store.propose(p)["status"] == "active"
    view = store.retrieve(states[4], "combat")
    assert len(view["skills"]) == 1
    upgraded = states[4].model_copy(
        update={
            "combat": states[4].combat.model_copy(
                update={"hand": tuple(c.model_copy(update={"upgraded": True}) for c in states[4].combat.hand)}
            )
        }
    )
    assert store.retrieve(upgraded, "combat")["skills"] == []
    assert held["id"] not in json.dumps(view)
    assert store.retrieve(states[4], "run")["skills"] == []
    contrary = evidence(store, states[4], "seed4", block=4)
    store.check_contradictions(contrary)
    assert store.inspect()["lessons"] == {"disabled": 1}
    assert store.retrieve(states[4], "combat")["skills"] == []
    assert memory.db.execute("SELECT COUNT(*) FROM lesson_history").fetchone()[0] == 3
    memory.close()


async def test_sqlite_thread_ownership_cancellation_and_loop_responsiveness(tmp_path, states):
    worker = await AsyncMemory.create(
        tmp_path / "memory.sqlite", tmp_path / "cards.sqlite", StrategyLibrary()
    )
    try:
        assert worker.thread_id != threading.get_ident()
        with pytest.raises(sqlite3.ProgrammingError):
            worker.store.db.execute("SELECT 1")
        job = asyncio.create_task(worker.call(lambda: time.sleep(0.04)))
        await asyncio.sleep(0.005)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
        assert (await worker.prepare(states[4], "combat")).instance_id
    finally:
        await worker.close()


def test_public_evidence_is_idempotent_and_promotes_without_holdout(tmp_path):
    from importlib.resources import files
    from pathlib import Path

    store = MemoryStore(tmp_path / "memory.sqlite")
    experience = ExperienceStore(store.db)
    path = Path(str(files("spiremind").joinpath("knowledge/benchmarks/training_evidence.json")))
    first = import_evidence(experience, path)
    second = import_evidence(experience, path)
    assert first["inserted"] == 686 and second["inserted"] == 0
    experience.consolidate()
    assert experience.inspect()["lessons"] == {"active": 2}
    assert set(experience.inspect()["episodes"]) == {"train"}
    value = json.loads(path.read_text(encoding="utf-8"))
    value["episodes"][0]["observations"]["hp_delta"] = 99999
    invalid = tmp_path / "bad.json"
    invalid.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="arithmetic"):
        import_evidence(experience, invalid)
    assert store.db.execute("SELECT COUNT(*) FROM episodes").fetchone()[0] == 686
    store.close()


async def test_combat_private_goal_cannot_write_runtime_hp_flag(states, tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite")
    manager = MemoryManager(store)
    state = states[4]
    context = await manager.context_for(state, "combat")
    audit = await manager.update(
        state,
        state.legal_actions[0],
        state,
        StrategyUpdate(current_goal="Survive this turn"),
        producer="combat",
        expected_policy_version=context.policy_version,
    )
    assert audit["applied"] == {"current_goal": "Survive this turn"}
    assert manager.run.policy_version == 0
    assert manager.working.lost_hp_this_turn is False
    store.close()


async def test_same_seed_new_instances_do_not_inflate_lesson_support(states, tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite")
    manager = MemoryManager(store)
    manager.experience = ExperienceStore(store.db)
    state = states[4]
    action = next(a for a in state.legal_actions if a.card_id == "c1")
    after = state.model_copy(
        update={
            "revision": state.revision + 1,
            "decision_id": "new",
            "combat": state.combat.model_copy(update={"block": state.combat.block + 5}),
        }
    )
    instances = set()
    for _ in range(3):
        manager.begin_run(state)
        instances.add(manager.run.instance_id)
        await manager.update(state, action, after, producer="combat")
    assert len(instances) == 3
    assert store.db.execute("SELECT COUNT(*) FROM episodes").fetchone()[0] == 3
    assert store.db.execute("SELECT COUNT(DISTINCT lineage) FROM episodes").fetchone()[0] == 1
    assert manager.experience.consolidate() == []
    store.close()


async def test_reflection_bounded_queue_cancellation_and_resume(tmp_path, states):
    worker = await AsyncMemory.create(
        tmp_path / "memory.sqlite", tmp_path / "cards.sqlite", StrategyLibrary()
    )

    def prepare_jobs():
        for n in range(12):
            evidence(worker.experience, states[4], f"seed{n}")
            worker.experience.enqueue(f"seed{n}")

    await worker.call(prepare_jobs)
    started = asyncio.Event()

    class Slow:
        async def reflect(self, data):
            started.set()
            await asyncio.Event().wait()

    first = ReflectionAgent(worker, Slow())
    await first.notify()
    await asyncio.wait_for(started.wait(), 2)
    assert first.queue.qsize() <= 8
    first.task.cancel()
    await asyncio.gather(first.task, return_exceptions=True)
    await first.close()
    assert (await worker.call(worker.experience.inspect))["reflection_jobs"] == {"pending": 12}
    completed = asyncio.Event()

    class Fast:
        calls = 0

        async def reflect(self, data):
            self.calls += 1
            if self.calls == 12:
                completed.set()
            return []

    provider = Fast()
    second = ReflectionAgent(worker, provider)
    await second.notify()
    await asyncio.wait_for(completed.wait(), 5)
    await second.close()
    assert (await worker.call(worker.experience.inspect))["reflection_jobs"] == {"complete": 12}
    await worker.close()


async def test_trace_backpressure_cancel_drain_and_failure(tmp_path):
    trace = AsyncTraceWriter(tmp_path, "test", capacity=2)
    original = trace._write_batch

    def slow(batch):
        time.sleep(0.01)
        original(batch)

    trace._write_batch = slow
    producers = [asyncio.create_task(trace.append("rows.jsonl", {"n": n})) for n in range(50)]
    await asyncio.gather(*producers)
    closing = asyncio.create_task(trace.close())
    await asyncio.sleep(0)
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing
    assert len((trace.path / "rows.jsonl").read_text().splitlines()) == 50
    assert trace.max_depth == 2
    broken = AsyncTraceWriter(tmp_path, "broken")

    def fail(batch):
        raise OSError("injected")

    broken._write_batch = fail
    await broken.append("rows.jsonl", {})
    with pytest.raises(TraceWriteError):
        await asyncio.wait_for(broken.flush(), 2)
    with pytest.raises(TraceWriteError):
        await broken.close()


async def test_trace_failure_settles_flush_queued_during_handle_close(tmp_path):
    trace = AsyncTraceWriter(tmp_path, "late-flush")
    loop = asyncio.get_running_loop()
    writing = asyncio.Event()
    closing_handles = asyncio.Event()
    flush_queued = asyncio.Event()
    allow_failure = threading.Event()
    allow_close = threading.Event()
    original_put = trace.queue.put

    def fail(batch):
        loop.call_soon_threadsafe(writing.set)
        assert allow_failure.wait(2)
        raise OSError("injected")

    def close_handles():
        loop.call_soon_threadsafe(closing_handles.set)
        assert allow_close.wait(2)

    async def delayed_put(item):
        if item[0] == "flush":
            await closing_handles.wait()
        await original_put(item)
        if item[0] == "flush":
            flush_queued.set()

    trace._write_batch = fail
    trace._close_handles = close_handles
    trace.queue.put = delayed_put
    await trace.append("rows.jsonl", {})
    await asyncio.wait_for(writing.wait(), 2)
    flush = asyncio.create_task(trace.flush())
    await asyncio.sleep(0)
    allow_failure.set()
    await asyncio.wait_for(flush_queued.wait(), 2)
    allow_close.set()
    with pytest.raises(TraceWriteError):
        await asyncio.wait_for(flush, 2)
    with pytest.raises(TraceWriteError):
        await trace.close()


async def test_budget_checks_before_http_and_invalid_json_reuses_calculator(monkeypatch):
    monkeypatch.setenv("TEST_KEY", "test")
    settings = ModelConfig(model="test", api_key_env="TEST_KEY", attempts=2, max_tokens=128)
    context = AgentContext("x", "JSON", "Choose A", 10, (), ())
    requests = []

    def transport(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            message = {
                "content": None,
                "tool_calls": [
                    {
                        "id": "t",
                        "type": "function",
                        "function": {"name": "calculate", "arguments": '{"expressions":["2+3"]}'},
                    }
                ],
            }
        elif len(requests) == 2:
            message = {"content": "bad JSON"}
        else:
            message = {"content": '{"action_id":"A","reason":"5","confidence":1}'}
        return httpx.Response(
            200,
            json={
                "model": "test",
                "choices": [{"message": message, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5},
            },
        )

    provider = OpenAIProvider(
        settings, httpx.AsyncClient(transport=httpx.MockTransport(transport)), RequestBudget(3, 10000)
    )
    result = await provider.choose(context, {"A"})
    assert result.choice.action_id == "A" and provider.calculator_calls == 1
    assert requests[2]["tool_choice"] == "auto"
    assert sum(m["role"] == "tool" for m in requests[2]["messages"]) == 1
    with pytest.raises(BudgetExceeded):
        await provider.choose(context, {"A"})
    assert len(requests) == 3
    assert provider.budget.tokens == 75 and len(provider.request_records) == 3
    assert retry_after_seconds("3") == 3
    await provider.close()
