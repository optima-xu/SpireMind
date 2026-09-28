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
from spiremind.environment.mcp import MCPEnvironment
from spiremind.environment.mock import MockEnvironment
from spiremind.knowledge.cards import CardDB
from spiremind.knowledge.enemies import EnemyKnowledge
from spiremind.knowledge.library import StrategyLibrary
from spiremind.memory.manager import MemoryManager
from spiremind.memory.storage_sqlite import MemoryStore
from spiremind.providers.openai import OpenAIProvider
from spiremind.runtime.agent import AgentRuntime
from spiremind.runtime.locking import SingleWriter
from spiremind.runtime.router import SceneRouter
from spiremind.runtime.trace import TraceWriter, replay_summary
from spiremind.strategies.combat import CombatStrategy
from spiremind.strategies.event import EventStrategy
from spiremind.strategies.fallback import conservative_choice
from spiremind.strategies.map import MapStrategy
from spiremind.strategies.run import DeckAnalyzer, RunStrategy


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


async def execute(args):
    config = Config.load(args.config)
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
                    "Return JSON only.",
                    'Return {"action_id":"probe_ok","reason":"ok","confidence":1.0}.',
                    60,
                    (),
                    (),
                ),
                {"probe_ok"},
            )
            report = dict(
                requested_model=config.model.model,
                resolved_model=result.model,
                valid_action=result.choice.action_id == "probe_ok",
                reasoning_present=result.reasoning_present,
                input_tokens=provider.input_tokens,
                output_tokens=provider.output_tokens,
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
                with SingleWriter(live_lock):
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
        with SingleWriter(live_lock):
            db = CardDB(root / "cards.sqlite")
            try:
                return {"imported": db.import_json(args.path)}
            finally:
                db.close()
    data = config.model_dump(mode="python")
    if args.max_steps is not None:
        data["runtime"]["max_steps"] = args.max_steps
    if args.character:
        data["game"]["character"] = args.character
    if args.ascension is not None:
        data["game"]["ascension"] = args.ascension
    if args.command == "step":
        data["runtime"]["max_steps"] = 1
    config = Config.model_validate(data)
    is_mock = args.environment == "mock"
    mode = ("mock_model" if args.policy == "model" else "mock_rules") if is_mock else "live"
    run_lock = root / "mock.lock" if is_mock else live_lock
    with SingleWriter(run_lock):
        trace = TraceWriter(
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
            env = MockEnvironment() if is_mock else MCPEnvironment(config.game, root / f"pending-{key}.json")
            if not is_mock:
                stack.push_async_callback(env.close)
            store = MemoryStore(root / ("mock-memory.sqlite" if is_mock else "memory.sqlite"))
            stack.callback(store.close)
            cards = CardDB(root / "cards.sqlite")
            stack.callback(cards.close)
            enemy_knowledge = EnemyKnowledge()
            if not is_mock:
                health = await env.health()
                trace.write_json("bridge-health.json", health)
                env.raw_sink = lambda state: trace.append("bridge-observations.jsonl", state)
                facts = await env.card_facts()
                if cards.needs_sync(env.game_version, facts=facts):
                    cards.put_many(facts)
                trace.write_json(
                    "knowledge.json",
                    {
                        "game_version": env.game_version,
                        "card_facts": cards.count(env.game_version),
                        "metadata": cards.metadata(env.game_version),
                        "enemy_knowledge": enemy_knowledge.metadata(),
                    },
                )
            provider = OpenAIProvider(config.model) if args.policy == "model" else None
            if provider:
                stack.push_async_callback(provider.close)
            library = StrategyLibrary()
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
            runtime = AgentRuntime(
                env,
                MemoryManager(store),
                SceneRouter(*strategies),
                DeckAnalyzer(library),
                trace,
                config,
                provider,
            )
            return await runtime.run()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="spiremind", description="SpireMind autonomous STS2 runtime")
    parser.add_argument(
        "--config", type=Path, help="TOML config; defaults to generic environment-based settings"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("run", "step"):
        p = sub.add_parser(command)
        p.add_argument("--environment", choices=("live", "mock"), default="live")
        p.add_argument("--policy", choices=("model", "rules"), default="model")
        p.add_argument("--max-steps", type=int)
        p.add_argument("--character", choices=("ironclad", "silent", "regent", "necrobinder", "defect"))
        p.add_argument("--ascension", type=int)
    for command in ("doctor", "observe", "probe-model", "sync-card-db"):
        sub.add_parser(command)
    for command in ("replay", "import-card-db"):
        sub.add_parser(command).add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        result = asyncio.run(execute(args))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "run" and not result.get("complete"):
            raise SystemExit(2)
    except KeyboardInterrupt:
        print("Stopped; trace and any pending action were preserved.")
        raise SystemExit(130) from None
    except Exception as error:
        # Avoid accidental key/transport-detail disclosure from arbitrary exception strings.
        print(f"SpireMind stopped: {type(error).__name__}. Check config, bridge and runs/ evidence.")
        if isinstance(error, (ValueError, RuntimeError)) and not isinstance(error, OSError):
            print(str(error)[:300])
        raise SystemExit(1) from None
