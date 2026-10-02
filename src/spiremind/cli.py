import argparse
import asyncio
import hashlib
import json
import sys
import tempfile
from contextlib import AsyncExitStack
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from spiremind.config import Config
from spiremind.context.budget import ContextBudget
from spiremind.context.compiler import AgentContext, ContextCompiler
from spiremind.core.enums import ActionKind, Scene
from spiremind.core.env_file import load_env_file
from spiremind.environment.mcp import MCPEnvironment
from spiremind.environment.mock import MockEnvironment
from spiremind.knowledge.cards import CardDB
from spiremind.knowledge.enemies import EnemyKnowledge
from spiremind.knowledge.library import StrategyLibrary
from spiremind.memory.async_store import AsyncMemory
from spiremind.memory.experience import ExperienceStore, import_history
from spiremind.memory.reflection import ReflectionAgent
from spiremind.memory.storage_sqlite import MemoryStore
from spiremind.providers.openai import OpenAIProvider
from spiremind.providers.protocols import RequestBudget
from spiremind.runtime.agent import AgentRuntime
from spiremind.runtime.async_trace import AsyncTraceWriter
from spiremind.runtime.control import RunControl, control_status, read_control, request_control, writer_active
from spiremind.runtime.locking import SingleWriter
from spiremind.runtime.router import SceneRouter
from spiremind.runtime.trace import replay_summary
from spiremind.strategies.combat import CombatStrategy
from spiremind.strategies.event import EventStrategy
from spiremind.strategies.fallback import conservative_choice
from spiremind.strategies.map import MapStrategy
from spiremind.strategies.run import RunStrategy


def canonical_bridge_url(value: str) -> str:
    """Return one lock identity for equivalent bridge base URLs."""
    parsed = urlsplit(value.strip())
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = parsed.port
    if port is not None and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    path = parsed.path.rstrip("/")
    return urlunsplit((scheme, host, path, "", ""))


def bridge_key(base_url: str) -> str:
    return hashlib.sha256(canonical_bridge_url(base_url).encode()).hexdigest()[:12]


def bridge_lock_path(base_url: str) -> Path:
    return Path(tempfile.gettempdir()) / "spiremind-locks" / f"bridge-{bridge_key(base_url)}.lock"


def safe_extra_body(value: dict) -> dict:
    sensitive = ("key", "token", "secret", "authorization", "password")

    def clean(item):
        if isinstance(item, dict):
            return {
                key: clean(child)
                for key, child in item.items()
                if not any(part in key.lower() for part in sensitive)
            }
        if isinstance(item, list):
            return [clean(child) for child in item]
        return item

    return clean(value)


def load_cli_config(config_path):
    if config_path is None and Path("config.local.toml").is_file():
        config_path = Path("config.local.toml")
    load_env_file((config_path.parent if config_path else Path.cwd()) / ".env")
    return Config.load(config_path)


async def execute(args):
    config = load_cli_config(args.config)
    if args.command == "benchmark":
        from spiremind.benchmark import benchmark

        return await benchmark(args, config)
    if args.command == "memory":
        path = args.database or config.runtime.runs_dir / "memory.sqlite"
        with SingleWriter(path.with_suffix(".maintenance.lock")):
            store = MemoryStore(path)
            try:
                experience = ExperienceStore(store.db)
                if args.memory_command == "import":
                    if args.path.is_file():
                        from spiremind.memory.evidence_io import import_evidence

                        return import_evidence(experience, args.path)
                    return import_history(experience, args.path)
                if args.memory_command == "consolidate":
                    if args.use_model:
                        from spiremind.memory.commands import consolidate_model

                        return await consolidate_model(experience, config)
                    results = experience.consolidate()
                    return {"proposals": len(results), "memory": experience.inspect()}
                return experience.inspect()
            finally:
                store.close()
    if args.command == "replay":
        return replay_summary(args.path)
    root = config.runtime.runs_dir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    key = bridge_key(config.game.base_url)
    live_lock = bridge_lock_path(config.game.base_url)
    if args.command == "probe-model":
        provider = OpenAIProvider(config.model)
        try:
            result = await provider.choose(
                AgentContext(
                    "probe",
                    "Use the calculate tool for arithmetic, then return one JSON decision.",
                    "A target has 48 HP and takes 11 damage. Calculate remaining HP. "
                    "Choose probe_ok if it is 37, otherwise probe_bad. Return JSON with "
                    "action_id, reason and confidence.",
                    60,
                    (),
                    (),
                ),
                {"probe_ok", "probe_bad"},
            )
            report = dict(
                requested_model=config.model.model,
                resolved_model=result.model,
                valid_action=result.choice.action_id == "probe_ok",
                reasoning_present=result.reasoning_present,
                input_tokens=provider.input_tokens,
                output_tokens=provider.output_tokens,
                calculator_calls=provider.calculator_calls,
                calculations=list(result.calculations),
            )
            (root / "model-probe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            return report
        finally:
            await provider.close()
    if args.command in {"doctor", "observe", "sync-card-db"}:
        env = MCPEnvironment(config.game, root / f"pending-{key}.json")
        try:
            health = await env.health()
            if args.command == "sync-card-db":
                with SingleWriter(live_lock), SingleWriter(root / "cards.maintenance.lock"):
                    db = CardDB(root / "cards.sqlite")
                    try:
                        db.put_many(await env.card_facts())
                        return {"game_version": env.game_version, "cards": db.count(env.game_version)}
                    finally:
                        db.close()
            if args.command == "doctor":
                return {
                    k: health.get(k)
                    for k in (
                        "game_version",
                        "mod_version",
                        "protocol_version",
                        "state_version",
                        "decision_version",
                        "compatibility",
                    )
                }
            state = await env.observe()
            return state.model_dump(mode="json")
        finally:
            await env.close()
    if args.command == "import-card-db":
        with SingleWriter(live_lock), SingleWriter(root / "cards.maintenance.lock"):
            db = CardDB(root / "cards.sqlite")
            try:
                return {"imported": db.import_json(args.path)}
            finally:
                db.close()
    is_mock = args.environment == "mock"
    run_lock = root / "mock.lock" if is_mock else live_lock
    control_path = run_lock.with_suffix(".control.json")
    if args.command == "status":
        return control_status(control_path, run_lock)
    if args.command == "pause":
        return request_control(control_path, run_lock, "paused")
    if args.command == "resume" and writer_active(run_lock):
        if (
            args.character
            or args.ascension is not None
            or args.policy
            or args.max_steps is not None
            or getattr(args, "no_limits", False)
        ):
            raise ValueError("Resuming a running agent keeps its settings. Omit launch overrides.")
        return request_control(control_path, run_lock, "running")
    previous = read_control(control_path).get("settings", {}) if args.command == "resume" else {}
    if not isinstance(previous, dict):
        raise ValueError("Invalid previous agent settings")
    data = config.model_dump(mode="python")
    if args.max_steps is not None:
        data["runtime"]["max_steps"] = args.max_steps
    if args.character or previous.get("character"):
        data["game"]["character"] = args.character or previous["character"]
    if args.ascension is not None or previous.get("ascension") is not None:
        data["game"]["ascension"] = args.ascension if args.ascension is not None else previous["ascension"]
    if getattr(args, "no_limits", False):
        data["runtime"].update(max_steps=None, max_seconds=None, max_total_tokens=None)
    if args.command == "step":
        data["runtime"]["max_steps"] = 1
    config = Config.model_validate(data)
    policy = args.policy or previous.get("policy", "model")
    mode = ("mock_model" if policy == "model" else "mock_rules") if is_mock else "live"
    with SingleWriter(run_lock):
        trace = AsyncTraceWriter(
            root,
            mode,
            configuration={
                "model": {
                    "base_url": config.model.base_url,
                    "model": config.model.model,
                    "timeout_seconds": config.model.timeout_seconds,
                    "attempts": config.model.attempts,
                    "max_tokens": config.model.max_tokens,
                    "max_completion_tokens": config.model.max_completion_tokens,
                    "temperature": config.model.temperature,
                    "json_mode": config.model.json_mode,
                    "calculator_mode": config.model.calculator_mode,
                    "require_exact_model": config.model.require_exact_model,
                    "extra_body": safe_extra_body(config.model.extra_body),
                },
                "game": {
                    "base_url": canonical_bridge_url(config.game.base_url),
                    "character": config.game.character,
                    "ascension": config.game.ascension,
                },
                "runtime": config.runtime.model_dump(mode="json"),
                "strategy": config.strategy.model_dump(mode="json"),
            },
        )
        async with AsyncExitStack() as stack:
            stack.push_async_callback(trace.close)
            env = MockEnvironment() if is_mock else MCPEnvironment(config.game, root / f"pending-{key}.json")
            if not is_mock:
                stack.push_async_callback(env.close)
            if args.command in {"start", "resume"}:
                if not is_mock:
                    await env.health()
                validate_entry(await env.observe(), args.command)
            control = stack.enter_context(
                RunControl(
                    control_path,
                    {
                        "character": config.game.character,
                        "ascension": config.game.ascension,
                        "policy": policy,
                        "runtime_limits": {
                            key: getattr(config.runtime, key)
                            for key in ("max_steps", "max_seconds", "max_total_tokens")
                        },
                    },
                )
            )
            library = StrategyLibrary()
            memory_path = root / ("mock-memory.sqlite" if is_mock else "memory.sqlite")
            stack.enter_context(SingleWriter(memory_path.with_suffix(".maintenance.lock")))
            stack.enter_context(SingleWriter(root / "cards.maintenance.lock"))
            memory = await AsyncMemory.create(
                root / ("mock-memory.sqlite" if is_mock else "memory.sqlite"), root / "cards.sqlite", library
            )
            stack.push_async_callback(memory.close)
            cards = memory.card_gateway
            enemy_knowledge = EnemyKnowledge()
            if not is_mock:
                health = await env.health()
                await trace.write_json("bridge-health.json", health)
                env.raw_sink = lambda state: trace.append("bridge-observations.jsonl", state)
                facts = await env.card_facts()
                await cards.sync(env.game_version, facts)
                await trace.write_json(
                    "knowledge.json",
                    {
                        "game_version": env.game_version,
                        "card_facts": await cards.count(env.game_version),
                        "metadata": await cards.metadata(env.game_version),
                        "enemy_knowledge": enemy_knowledge.metadata(),
                    },
                )
            provider = OpenAIProvider(config.model) if policy == "model" else None
            if provider:
                stack.push_async_callback(provider.close)
            compiler = ContextCompiler(
                library,
                cards,
                ContextBudget(config.runtime.context_tokens, config.runtime.max_context_tokens),
                enemy_knowledge,
            )
            strategies = [
                (
                    cls(compiler, provider, conservative_choice, config.strategy)
                    if cls is CombatStrategy
                    else cls(compiler, provider, conservative_choice)
                )
                for cls in (CombatStrategy, RunStrategy, MapStrategy, EventStrategy)
            ]
            shared_budget = RequestBudget(None, config.runtime.max_total_tokens)
            if provider:
                provider.budget = shared_budget
            reflection_provider = None
            if config.memory.reflection_use_model:
                reflection_provider = OpenAIProvider(
                    config.model,
                    budget=RequestBudget(
                        config.memory.reflection_requests,
                        config.memory.reflection_tokens,
                        parent=shared_budget,
                    ),
                )
                stack.push_async_callback(reflection_provider.close)
            reflection = ReflectionAgent(memory, reflection_provider)
            stack.push_async_callback(reflection.close)
            await reflection.notify()
            runtime = AgentRuntime(
                env,
                memory,
                SceneRouter(*strategies),
                None,
                trace,
                config,
                provider,
                reflection,
                control=control,
                new_run=args.command == "start",
            )
            result = await runtime.run()
            await reflection.close()
            result["storage"] = await memory.stats()
            result["reflection"] = dict(
                completed=reflection.completed,
                rejected=reflection.rejected,
                model_calls=reflection_provider.calls if reflection_provider else 0,
                input_tokens=reflection_provider.input_tokens if reflection_provider else 0,
                output_tokens=reflection_provider.output_tokens if reflection_provider else 0,
            )
            result["request_budget"] = shared_budget.report()
            if reflection_provider:
                await trace.write_json("reflection-requests.json", reflection_provider.request_records)
            await trace.write_json("summary.json", result)
            await trace.flush()
            return result


def validate_entry(state, command):
    if command == "start":
        if state.scene != Scene.MAIN_MENU or not any(
            a.kind in {ActionKind.OPEN_RUN, ActionKind.CONTINUE_RUN} for a in state.legal_actions
        ):
            raise ValueError(
                "Please return to the game's main menu before start. 请先返回游戏首页再启动 Agent。"
            )
        if any(a.kind == ActionKind.CONTINUE_RUN for a in state.legal_actions):
            raise ValueError(
                "An existing run is available. Use resume, or finish/abandon it in the game first."
            )
    elif (
        state.terminal
        or state.scene == Scene.UNKNOWN
        or (
            state.scene == Scene.MAIN_MENU
            and not any(a.kind == ActionKind.CONTINUE_RUN for a in state.legal_actions)
        )
    ):
        raise ValueError(
            "No run to resume. Return to the main menu and use start. 请先返回首页并使用 start。"
        )


def build_parser():
    parser = argparse.ArgumentParser(prog="spiremind", description="SpireMind autonomous STS2 runtime")
    parser.add_argument(
        "--config", type=Path, help="TOML config; auto-loads config.local.toml and .env when present"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    descriptions = {
        "start": "Start a new run from the game's main menu",
        "resume": "Resume a paused agent or reconnect to an unfinished run",
        "run": "Legacy entry: continue an existing run or create one",
        "step": "Execute at most one decision from the current state",
    }
    for command in ("start", "run", "step", "resume"):
        p = sub.add_parser(command, help=descriptions[command], description=descriptions[command])
        p.add_argument("--environment", choices=("live", "mock"), default="live")
        p.add_argument(
            "--policy", choices=("model", "rules"), default=None if command == "resume" else "model"
        )
        p.add_argument("--max-steps", type=int)
        if command != "step":
            p.add_argument(
                "--no-limits", action="store_true", help="Disable step, elapsed-time and total-token limits"
            )
        if command == "resume":
            p.set_defaults(character=None, ascension=None)
        else:
            p.add_argument("--character", choices=("ironclad", "silent", "regent", "necrobinder", "defect"))
            p.add_argument("--ascension", type=int, help="Unlocked ascension level; 0 is base difficulty")
    for command in ("pause", "status"):
        description = "Pause at a safe boundary" if command == "pause" else "Read the agent control status"
        sub.add_parser(command, help=description).add_argument(
            "--environment", choices=("live", "mock"), default="live"
        )
    for command in ("doctor", "observe", "probe-model", "sync-card-db"):
        sub.add_parser(command)
    for command in ("replay", "import-card-db"):
        sub.add_parser(command).add_argument("path", type=Path)
    memory = sub.add_parser("memory", help="Import, reflect on or inspect experience")
    memory.add_argument("--database", type=Path)
    commands = memory.add_subparsers(dest="memory_command", required=True)
    commands.add_parser("import").add_argument("path", type=Path)
    commands.add_parser("inspect")
    commands.add_parser("consolidate").add_argument("--use-model", action="store_true")
    bench = sub.add_parser("benchmark", help="Offline by default; model calls require --use-model")
    bench.add_argument("--use-model", action="store_true")
    bench.add_argument("--baseline", type=Path)
    bench.add_argument("--dataset", type=Path)
    bench.add_argument("--memory-db", type=Path)
    bench.add_argument("--output", type=Path, default=Path("runs/benchmarks/latest.json"))
    bench.add_argument("--rounds", type=int, default=15)
    return parser


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    try:
        result = asyncio.run(execute(args))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if (
            args.command in {"run", "start", "resume"}
            and not result.get("complete")
            and "status" not in result
        ):
            raise SystemExit(2)
    except KeyboardInterrupt:
        print("Stopped; trace and any pending action were preserved. Use resume to continue the current run.")
        raise SystemExit(130) from None
    except Exception as error:
        # Avoid accidental key/transport-detail disclosure from arbitrary exception strings.
        print(f"SpireMind stopped: {type(error).__name__}. Check config, bridge and runs/ evidence.")
        if isinstance(error, (ValueError, RuntimeError)) and not isinstance(error, OSError):
            print(str(error)[:300])
        raise SystemExit(1) from None
