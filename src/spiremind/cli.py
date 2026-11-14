"""Minimal SpireMind CLI exposing `ui` (default), `play`, and `doctor`."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
import webbrowser
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import uvicorn

from spiremind import __version__
from spiremind.agent.session import AgentSession
from spiremind.bridge.client import probe_bridge
from spiremind.config import Config, api_key_status, load_config
from spiremind.llm.client import probe_llm
from spiremind.server.app import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spiremind",
        description="SpireMind: Slay the Spire 2 AI Agent & Local Cockpit",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command")

    ui_p = sub.add_parser("ui", help="Start the local Web UI server (default)")
    ui_p.add_argument(
        "--config", type=Path, default=None, help="Path to TOML config (default: config.local.toml)"
    )
    ui_p.add_argument("--host", type=str, default=None, help="Bind host (default from config or 127.0.0.1)")
    ui_p.add_argument("--port", type=int, default=None, help="Bind port (default from config or 8765)")
    ui_p.add_argument("--no-browser", action="store_true", help="Do not automatically open the browser")

    play_p = sub.add_parser("play", help="Run the agent headlessly in the terminal")
    play_p.add_argument("--config", type=Path, default=None, help="Path to TOML config")
    play_p.add_argument("--character", type=str, default=None, help="Override configured character")
    play_p.add_argument("--ascension", type=int, default=None, help="Override configured ascension")
    play_p.add_argument("--policy", choices=("model", "rules"), default="model", help="Decision policy")
    play_p.add_argument(
        "--attach", action="store_true", help="Attach to an active/saved run instead of starting new"
    )
    play_p.add_argument("--max-steps", type=int, default=None, help="Maximum steps before stopping")

    doc_p = sub.add_parser(
        "doctor", help="Check local configuration, game bridge, and optional LLM connectivity"
    )
    doc_p.add_argument("--config", type=Path, default=None, help="Path to TOML config")
    doc_p.add_argument(
        "--check-llm", action="store_true", help="Send a minimal probe request to the configured LLM"
    )

    return parser


def _apply_play_overrides(cfg: Config, args: argparse.Namespace) -> Config:
    raw = cfg.model_dump()
    if args.character is not None:
        raw["game"]["character"] = args.character
    if args.ascension is not None:
        raw["game"]["ascension"] = args.ascension
    if args.max_steps is not None:
        raw["runtime"]["max_steps"] = args.max_steps
    return Config.model_validate(raw)


def _open_browser_soon(url: str) -> None:
    timer = threading.Timer(1.0, lambda: webbrowser.open(url))
    timer.daemon = True
    timer.start()


def _cmd_ui(args: argparse.Namespace) -> int:
    cfg_path = getattr(args, "config", None) or Path("config.local.toml")
    env_path = Path(".env")
    cfg = load_config(cfg_path if cfg_path.exists() else None, env_path=env_path)
    host = getattr(args, "host", None) or cfg.server.host
    port = getattr(args, "port", None) or cfg.server.port
    app = create_app(cfg, config_path=cfg_path, env_path=env_path)
    if not getattr(args, "no_browser", False):
        _open_browser_soon(f"http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


async def _cmd_play(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    cfg = _apply_play_overrides(cfg, args)
    session = AgentSession(cfg)
    summary = await session.run_until_done(
        run_mode="attach" if args.attach else "start",
        policy=args.policy,
        validate_initial=True,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0 if summary.get("outcome") != "error" else 1


async def _cmd_doctor(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    bridge_report = await probe_bridge(cfg.game.base_url, timeout_seconds=cfg.game.timeout_seconds)
    report: dict[str, Any] = {
        "version": __version__,
        "model": cfg.model.model,
        "base_url": cfg.model.base_url,
        "api_key": api_key_status(cfg.model.api_key_env),
        "bridge": bridge_report,
    }
    ok = bool(bridge_report.get("ok"))
    if args.check_llm:
        llm_report = await probe_llm(cfg.model)
        report["llm"] = llm_report
        ok = ok and bool(llm_report.get("ok"))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    command = args.command or "ui"
    if command == "ui":
        return _cmd_ui(args)
    if command == "play":
        return asyncio.run(_cmd_play(args))
    if command == "doctor":
        return asyncio.run(_cmd_doctor(args))
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
