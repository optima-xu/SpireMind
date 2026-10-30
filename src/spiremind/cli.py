import argparse
import asyncio
import json
import sys
from pathlib import Path

from spiremind.bootstrap import execute


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
    quality = sub.add_parser("evaluate", help="Offline labeled policy cases; never calls a model")
    quality.add_argument("--dataset", type=Path)
    quality.add_argument("--output", type=Path)
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
        if args.command == "evaluate" and result["passed"] != result["total"]:
            raise SystemExit(1)
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
