"""Run the same preparation probe in isolated baseline/current source processes."""

import argparse
import asyncio
import json
import statistics
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

from spiremind.context.budget import ContextBudget
from spiremind.context.compiler import ContextCompiler
from spiremind.core.state import GameState
from spiremind.knowledge.cards import CardDB, CardFact
from spiremind.knowledge.library import StrategyLibrary
from spiremind.memory.manager import MemoryManager
from spiremind.memory.storage_sqlite import MemoryStore
from spiremind.runtime.trace import TraceWriter, source_fingerprint
from spiremind.strategies.combat import CombatStrategy
from spiremind.strategies.combat_tactics import assess
from spiremind.strategies.event import EventStrategy
from spiremind.strategies.fallback import conservative_choice
from spiremind.strategies.map import MapStrategy
from spiremind.strategies.run import DeckAnalyzer, RunStrategy


def distribution(samples):
    ordered = sorted(samples)
    return dict(p50=statistics.median(ordered), p95=ordered[int((len(ordered) - 1) * 0.95)], n=len(ordered))


async def probe(args):
    data = json.loads(args.dataset.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        cards = CardDB(root / "cards.sqlite")
        cards.put_many([CardFact.model_validate(row) for row in data.get("cards", [])])
        store = MemoryStore(root / "memory.sqlite")
        library = StrategyLibrary()
        memory = MemoryManager(store, cards=cards)
        analyzer = DeckAnalyzer(library, cards)
        compiler = ContextCompiler(library, cards, ContextBudget(4000, 16000))
        learned_store = None
        if args.learning:
            import sqlite3

            from spiremind.memory.experience import ExperienceStore

            learned_store = sqlite3.connect(f"file:{args.learning.as_posix()}?mode=ro", uri=True)
            memory.experience = ExperienceStore(learned_store)
        sql = dict(queries=0, transactions=0)

        def count(statement):
            if statement.startswith("SELECT"):
                sql["queries"] += 1
            elif statement.startswith("BEGIN"):
                sql["transactions"] += 1

        store.db.set_trace_callback(count)
        cards.db.set_trace_callback(count)
        phases = {"cold": [], "warm": []}
        per_scene = {}
        contexts = {}
        card_queries = 0

        def card_count(statement):
            nonlocal card_queries
            count(statement)
            if statement.startswith("SELECT id,upgraded,payload"):
                card_queries += 1

        cards.db.set_trace_callback(card_count)
        for case in data["cases"]:
            state = GameState.model_validate(case["state"])
            agent = case["agent"]
            strategy = {
                "combat": CombatStrategy,
                "run": RunStrategy,
                "map": MapStrategy,
                "event": EventStrategy,
            }[agent](compiler, None, conservative_choice)
            for round_index in range(args.rounds + 1):
                if round_index == 0:
                    for object_ in (cards, analyzer, library, getattr(memory, "experience", None)):
                        if object_ is not None and hasattr(object_, "cache"):
                            object_.cache.clear()
                started = time.perf_counter_ns()
                memory.apply_analysis(state, analyzer.analyze(state))
                view = await memory.context_for(state, agent)
                if agent == "combat" and state.combat:
                    assessment = assess(state)
                    task = (
                        strategy.task_for(state, view, assessment)
                        if hasattr(analyzer, "cache")
                        else strategy.task_for(state, view)
                    )
                else:
                    task = strategy.task_for(state, view)
                context = await compiler.build(state, agent, view, task)
                elapsed = (time.perf_counter_ns() - started) / 1e6
                phase = "cold" if round_index == 0 else "warm"
                phases[phase].append(elapsed)
                per_scene.setdefault(state.scene.value, []).append(elapsed) if phase == "warm" else None
                contexts[case["id"]] = asdict(context)
        trace = TraceWriter(root / "traces", "benchmark")
        started = time.perf_counter()
        for index in range(1000):
            trace.append("rows.jsonl", {"n": index, "payload": "x" * 200})
        logging_ms = (time.perf_counter() - started) * 1000
        result = dict(
            source_sha256=source_fingerprint(),
            local_ms={k: distribution(v) for k, v in phases.items()},
            scenes_ms={k: distribution(v) for k, v in per_scene.items()},
            sql=sql,
            card_queries=card_queries,
            contexts=contexts,
            synchronous_log_1000_ms=logging_ms,
            caches={
                name: obj.cache.stats()
                for name, obj in [
                    ("cards", cards),
                    ("deck", analyzer),
                    ("retrieval", getattr(memory, "experience", None)),
                ]
                if obj is not None and hasattr(obj, "cache")
            },
        )
        if learned_store:
            learned_store.close()
        cards.close()
        store.close()
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=15)
    parser.add_argument("--learning", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(asyncio.run(probe(args)), ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
