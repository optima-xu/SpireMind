"""Reproducible offline preparation probe and explicitly budgeted model comparison."""

import asyncio
import hashlib
import json
import statistics
import sys
import tempfile
import time
from importlib.resources import files
from pathlib import Path

from spiremind.context.compiler import AgentContext
from spiremind.core.state import GameState
from spiremind.memory.experience import digest
from spiremind.providers.openai import OpenAIProvider, ProviderError
from spiremind.providers.protocols import BudgetExceeded, RequestBudget
from spiremind.runtime.async_trace import AsyncTraceWriter
from spiremind.runtime.trace import source_fingerprint

CURRENT_SOURCE = Path(__file__).resolve().parents[1]


async def production_probe(data, root):
    from spiremind.bench_worker import distribution
    from spiremind.context.budget import ContextBudget
    from spiremind.context.compiler import ContextCompiler
    from spiremind.knowledge.cards import CardFact
    from spiremind.knowledge.library import StrategyLibrary
    from spiremind.memory.async_store import AsyncMemory
    from spiremind.strategies.combat import CombatStrategy
    from spiremind.strategies.combat_tactics import assess
    from spiremind.strategies.event import EventStrategy
    from spiremind.strategies.fallback import conservative_choice
    from spiremind.strategies.map import MapStrategy
    from spiremind.strategies.run import RunStrategy

    library = StrategyLibrary()
    memory = await AsyncMemory.create(
        root / "async.sqlite", root / "async-cards.sqlite", library, learning=False
    )
    try:
        await memory.call(
            lambda: memory.cards.put_many([CardFact.model_validate(row) for row in data["cards"]])
        )
        compiler = ContextCompiler(library, memory.card_gateway, ContextBudget(4000, 16000))
        samples = []
        for case in data["cases"]:
            state = GameState.model_validate(case["state"])
            strategy = {
                "combat": CombatStrategy,
                "run": RunStrategy,
                "map": MapStrategy,
                "event": EventStrategy,
            }[case["agent"]](compiler, None, conservative_choice)
            for repeat in range(6):
                start = time.perf_counter()
                view = await memory.prepare(state, case["agent"])
                task = (
                    strategy.task_for(state, view, assess(state))
                    if case["agent"] == "combat" and state.combat
                    else strategy.task_for(state, view)
                )
                await compiler.build(state, case["agent"], view, task)
                if repeat:
                    samples.append((time.perf_counter() - start) * 1000)
        return dict(warm_ms=distribution(samples), storage=await memory.stats())
    finally:
        await memory.close()


def save(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


async def worker(source, dataset, output, rounds, learning=None):
    script = Path(__file__).with_name("bench_worker.py")
    command = [
        sys.executable,
        "-c",
        "import sys,runpy;sys.path.insert(0,sys.argv.pop(1));"
        "runpy.run_path(sys.argv.pop(1),run_name='__main__')",
        str(source),
        str(script),
        "--dataset",
        str(dataset),
        "--output",
        str(output),
        "--rounds",
        str(rounds),
    ]
    if learning:
        command += ["--learning", str(learning)]
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, error = await process.communicate()
    if process.returncode:
        raise RuntimeError("benchmark_worker_failed:" + error.decode(errors="replace")[-1500:])
    return json.loads(output.read_text(encoding="utf-8"))


async def model_comparison(report, arms, data, config, output):
    if config.model.model != "deepseek-v4-flash-0731":
        raise ValueError("Model comparison requires deepseek-v4-flash-0731")
    budget = RequestBudget(72, 360000)
    provider = OpenAIProvider(config.model, budget=budget)
    selected = [
        next(case for case in data["cases"] if case["id"] == key)
        for key in ("combat-1", "combat-2", "shop-1", "map-1")
    ]
    rows = []
    model_report = dict(
        planned_decisions=24,
        planned_groups=8,
        records=rows,
        budget=budget.report(),
        requests=[],
        complete_groups=0,
        complete=False,
        transport="common optimized transport; baseline/current contexts isolate prompt and memory changes",
        configuration=dict(
            model=config.model.model,
            extra_body=config.model.extra_body,
            calculator=config.model.calculator_mode,
            max_completion_tokens=config.model.max_completion_tokens,
        ),
    )
    report["model"] = model_report

    def checkpoint_requests():
        model_report.update(budget=budget.report(), requests=provider.request_records)
        save(output, report)

    provider.request_sink = checkpoint_requests
    stopped = False
    try:
        for repeat in range(2):
            order = ("A", "B", "C") if repeat == 0 else ("C", "B", "A")
            for case in selected:
                state = GameState.model_validate(case["state"])
                for arm in order:
                    if arm not in arms:
                        continue
                    context = AgentContext(**arms[arm]["contexts"][case["id"]])
                    started = time.perf_counter()
                    before_input, before_output = provider.input_tokens, provider.output_tokens
                    before_calls = provider.calls
                    row = dict(case=case["id"], repeat=repeat, arm=arm, valid=False, complete=False)
                    try:
                        result = await provider.choose(context, {a.id for a in state.legal_actions})
                        row.update(
                            complete=True,
                            valid=result.choice.action_id in {a.id for a in state.legal_actions},
                            action_id=result.choice.action_id,
                            reason=result.choice.reason,
                            calculator_calls=len(result.calculations),
                            resolved_model=result.model,
                        )
                        if state.combat:
                            from spiremind.strategies.combat_tactics import assess

                            facts = assess(state)
                            chosen = next(
                                (
                                    a
                                    for a in facts.get("evaluated_actions", [])
                                    if a["action_id"] == result.choice.action_id
                                ),
                                None,
                            )
                            row["known_self_lethal"] = bool(chosen and chosen.get("self_lethal"))
                    except BudgetExceeded:
                        row["error"] = "budget_exhausted"
                        stopped = True
                    except ProviderError as error:
                        row["error"] = str(error)
                    row.update(
                        latency_ms=(time.perf_counter() - started) * 1000,
                        input_tokens=provider.input_tokens - before_input,
                        output_tokens=provider.output_tokens - before_output,
                        requests=provider.calls - before_calls,
                    )
                    rows.append(row)
                    groups = {}
                    for record in rows:
                        if record["complete"]:
                            groups.setdefault((record["case"], record["repeat"]), set()).add(record["arm"])
                    model_report.update(
                        budget=budget.report(),
                        requests=provider.request_records,
                        complete_groups=sum(group == {"A", "B", "C"} for group in groups.values()),
                    )
                    save(output, report)
                    print(
                        f"model decisions={len(rows)}/24 complete_groups={model_report['complete_groups']}/8 "
                        f"HTTP={budget.requests}/72 tokens={budget.tokens}/360000",
                        flush=True,
                    )
                    if stopped:
                        break
                if stopped:
                    break
            if stopped:
                break
        model_report["complete"] = model_report["complete_groups"] == 8
        # Only matched, completed A/B/C groups contribute to aggregate model comparisons.
        complete_keys = {key for key, value in groups.items() if value == {"A", "B", "C"}}
        model_report["paired_summary"] = {}
        for arm in ("A", "B", "C"):
            records = [r for r in rows if r["arm"] == arm and (r["case"], r["repeat"]) in complete_keys]
            if records:
                model_report["paired_summary"][arm] = dict(
                    n=len(records),
                    valid_actions=sum(r["valid"] for r in records),
                    median_latency_ms=statistics.median(r["latency_ms"] for r in records),
                    input_tokens=sum(r["input_tokens"] for r in records),
                    output_tokens=sum(r["output_tokens"] for r in records),
                )
    finally:
        await provider.close()
        save(output, report)


async def benchmark(args, config):
    if not 1 <= args.rounds <= 200:
        raise ValueError("rounds must be between 1 and 200")
    dataset = (
        args.dataset or Path(str(files("spiremind").joinpath("knowledge/benchmarks/public_states.json")))
    ).resolve()
    data = json.loads(dataset.read_text(encoding="utf-8"))
    output = args.output.resolve()
    report = dict(
        schema_version=1,
        mode="model" if args.use_model else "offline",
        source_sha256=source_fingerprint(),
        dataset_sha256=hashlib.sha256(dataset.read_bytes()).hexdigest(),
        config_sha256=digest(
            {
                "rounds": args.rounds,
                "context_target": 4000,
                "context_maximum": 16000,
                "model": config.model.model,
                "thinking": config.model.extra_body,
                "generation": config.model.model_dump(mode="json", exclude={"base_url", "api_key_env"}),
            }
        ),
        cases=len(data["cases"]),
        rounds=args.rounds,
        platform=sys.platform,
        python=sys.version.split()[0],
        notes=[
            "Local preparation excludes HTTP and game execution. "
            "Cold means cleared fact/deck/retrieval caches.",
            "All included historical observations belong to holdout lineages; learning reads train only.",
        ],
    )
    arms = {}
    current = CURRENT_SOURCE
    with tempfile.TemporaryDirectory(prefix="spiremind-benchmark-") as directory:
        root = Path(directory)
        sources = {"B": current}
        if args.baseline:
            sources = {"A": args.baseline.resolve() / "src", **sources}
        for arm, source in sources.items():
            arms[arm] = await worker(source, dataset, root / f"{arm}.json", args.rounds)
        memory_hash = None
        if args.memory_db:
            memory_path = args.memory_db.resolve()
            memory_hash = hashlib.sha256(memory_path.read_bytes()).hexdigest()
            arms["C"] = await worker(current, dataset, root / "C.json", args.rounds, memory_path)
            report["frozen_memory_sha256"] = memory_hash
        report["arms"] = {
            arm: {key: value for key, value in result.items() if key != "contexts"}
            for arm, result in arms.items()
        }
        report["context_tokens"] = {
            arm: {case: context["estimated_tokens"] for case, context in result["contexts"].items()}
            for arm, result in arms.items()
        }
        report["production_async_preparation"] = await production_probe(data, root)
        if "A" in arms:
            a, b = arms["A"], arms["B"]
            combat_cases = [c["id"] for c in data["cases"] if c["state"]["scene"] == "combat"]
            ratios = [
                1 - b["contexts"][c]["estimated_tokens"] / a["contexts"][c]["estimated_tokens"]
                for c in combat_cases
            ]
            report["improvements"] = dict(
                warm_p50_fraction=1 - b["local_ms"]["warm"]["p50"] / a["local_ms"]["warm"]["p50"],
                card_query_fraction=1 - b["card_queries"] / max(1, a["card_queries"]),
                combat_context_median_fraction=statistics.median(ratios),
            )
            report["targets_passed"] = dict(
                warm_p50=report["improvements"]["warm_p50_fraction"] >= 0.25,
                card_queries=report["improvements"]["card_query_fraction"] >= 0.8,
                combat_context=report["improvements"]["combat_context_median_fraction"] >= 0.15,
            )
        trace = AsyncTraceWriter(root / "async-trace", "benchmark")
        started = time.perf_counter()
        for index in range(1000):
            await trace.append("rows.jsonl", {"n": index, "payload": "x" * 200})
        await trace.close()
        report["async_log_1000_including_drain_ms"] = (time.perf_counter() - started) * 1000
        report["async_log_batches"] = trace.batches
        save(output, report)
        if args.use_model:
            if set(arms) != {"A", "B", "C"}:
                raise ValueError("Model A/B/C comparison requires --baseline and --memory-db")
            await model_comparison(report, arms, data, config, output)
        if memory_hash and hashlib.sha256(args.memory_db.resolve().read_bytes()).hexdigest() != memory_hash:
            raise RuntimeError("frozen_memory_changed_during_benchmark")
    return report
