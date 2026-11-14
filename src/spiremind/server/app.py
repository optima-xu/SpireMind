"""FastAPI application factory with CORS, WebSocket streaming, and built SPA static fallback."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from spiremind import __version__
from spiremind.agent.session import AgentSession
from spiremind.config import Config, load_config
from spiremind.server.routes import router


@dataclass
class AppContext:
    config: Config
    config_path: Path
    env_path: Path
    session: AgentSession


def _default_web_dist() -> Path:
    return Path(__file__).resolve().parents[3] / "web" / "dist"


def create_app(
    config: Config | None = None,
    *,
    config_path: Path | None = None,
    env_path: Path | None = None,
    session: AgentSession | None = None,
    web_dist_dir: Path | None = None,
) -> FastAPI:
    resolved_cfg_path = config_path or Path("config.local.toml")
    resolved_env_path = env_path or Path(".env")
    active_config = config or load_config(resolved_cfg_path, env_path=resolved_env_path)
    active_session = session or AgentSession(active_config)
    app_ctx = AppContext(
        config=active_config,
        config_path=resolved_cfg_path,
        env_path=resolved_env_path,
        session=active_session,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await app_ctx.session.stop()

    app = FastAPI(
        title="SpireMind Console API",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.ctx = app_ctx

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    dist = web_dist_dir or _default_web_dist()
    index_file = dist / "index.html"
    assets_dir = dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    if index_file.is_file():
        dist_resolved = dist.resolve()

        @app.get("/", include_in_schema=False)
        async def spa_index() -> FileResponse:
            return FileResponse(index_file)

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str) -> FileResponse:
            if full_path.startswith("api/") or full_path == "api":
                raise HTTPException(status_code=404, detail="Not found")
            candidate = (dist_resolved / full_path).resolve()
            if candidate != dist_resolved and dist_resolved in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index_file)
    else:

        @app.get("/", include_in_schema=False)
        async def api_root_notice() -> JSONResponse:
            return JSONResponse(
                {
                    "name": "SpireMind API",
                    "version": __version__,
                    "ui_built": False,
                    "hint": "Build the frontend (`pnpm --dir web run build`) or run Vite dev server.",
                }
            )

    return app
