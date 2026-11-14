"""REST and WebSocket routes powering the SpireMind local cockpit."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket
from pydantic import BaseModel, ConfigDict, ValidationError

from spiremind import __version__
from spiremind.agent.session import PolicyMode
from spiremind.bridge.client import probe_bridge
from spiremind.config import (
    PROVIDER_PRESETS,
    Config,
    api_key_status,
    redact_config,
    save_settings,
)
from spiremind.domain.decision import EnvironmentError
from spiremind.llm.client import probe_llm
from spiremind.server.stream import stream_session_events
from spiremind.storage.trace_store import TraceReader

if TYPE_CHECKING:
    from spiremind.server.app import AppContext

router = APIRouter(prefix="/api")


class RequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartRunRequest(RequestBody):
    character: str | None = None
    ascension: int | None = None
    policy: PolicyMode = "model"


class AttachRunRequest(RequestBody):
    policy: PolicyMode = "model"


class StepRequest(RequestBody):
    policy: PolicyMode | None = None


class UpdateSettingsRequest(RequestBody):
    model: dict[str, Any] | None = None
    game: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None
    strategy: dict[str, Any] | None = None
    server: dict[str, Any] | None = None
    new_api_key: str | None = None


class BridgeProbeRequest(RequestBody):
    base_url: str | None = None


class LlmProbeRequest(RequestBody):
    model: dict[str, Any] | None = None
    new_api_key: str | None = None


def _ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def _settings_payload(ctx: AppContext) -> dict[str, Any]:
    return {
        "config": redact_config(ctx.config),
        "api_key": api_key_status(ctx.config.model.api_key_env),
        "presets": PROVIDER_PRESETS,
        "config_path": str(ctx.config_path),
        "env_path": str(ctx.env_path),
    }


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    ctx = _ctx(request)
    return {
        "ok": True,
        "version": __version__,
        "status": ctx.session.status,
        "attempt_id": ctx.session.attempt_id,
    }


@router.get("/session")
async def get_session(request: Request) -> dict[str, Any]:
    return _ctx(request).session.snapshot()


@router.post("/session/start")
async def start_session(request: Request, body: StartRunRequest | None = None) -> dict[str, Any]:
    ctx = _ctx(request)
    payload = body or StartRunRequest()
    try:
        return await ctx.session.start_run(
            character=payload.character,
            ascension=payload.ascension,
            policy=payload.policy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@router.post("/session/attach")
async def attach_session(request: Request, body: AttachRunRequest | None = None) -> dict[str, Any]:
    ctx = _ctx(request)
    payload = body or AttachRunRequest()
    try:
        return await ctx.session.attach_run(policy=payload.policy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@router.post("/session/pause")
async def pause_session(request: Request) -> dict[str, Any]:
    return _ctx(request).session.pause()


@router.post("/session/resume")
async def resume_session(request: Request) -> dict[str, Any]:
    return _ctx(request).session.resume()


@router.post("/session/step")
async def step_session(request: Request, body: StepRequest | None = None) -> dict[str, Any]:
    ctx = _ctx(request)
    payload = body or StepRequest()
    try:
        result = await ctx.session.step_once(payload.policy)
        return {"result": result, "snapshot": ctx.session.snapshot()}
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@router.post("/session/stop")
async def stop_session(request: Request) -> dict[str, Any]:
    return await _ctx(request).session.stop()


@router.get("/bridge/observe")
async def observe_bridge(request: Request) -> dict[str, Any]:
    ctx = _ctx(request)
    try:
        await ctx.session.observe_once()
        return ctx.session.snapshot()
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None


@router.get("/settings")
async def get_settings(request: Request) -> dict[str, Any]:
    return _settings_payload(_ctx(request))


@router.put("/settings")
async def put_settings(request: Request, body: UpdateSettingsRequest) -> dict[str, Any]:
    ctx = _ctx(request)
    merged = ctx.config.model_dump()
    for section in ("model", "game", "runtime", "strategy", "server"):
        patch = getattr(body, section)
        if patch is not None:
            merged[section] = {**merged[section], **patch}
    try:
        updated = Config.model_validate(merged)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from None

    try:
        ctx.session.update_config(updated)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

    try:
        save_settings(updated, ctx.config_path, ctx.env_path, body.new_api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    ctx.config = updated
    return _settings_payload(ctx)


@router.post("/doctor/bridge")
async def doctor_bridge(request: Request, body: BridgeProbeRequest | None = None) -> dict[str, Any]:
    ctx = _ctx(request)
    url = (body.base_url if body and body.base_url else None) or ctx.config.game.base_url
    return await probe_bridge(url, timeout_seconds=ctx.config.game.timeout_seconds)


@router.post("/doctor/llm")
async def doctor_llm(request: Request, body: LlmProbeRequest | None = None) -> dict[str, Any]:
    ctx = _ctx(request)
    model_data = ctx.config.model.model_dump()
    if body and body.model:
        model_data.update(body.model)
    try:
        probe_cfg = ctx.config.model.__class__.model_validate(model_data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from None
    return await probe_llm(probe_cfg, api_key_override=body.new_api_key if body else None)


@router.get("/runs")
async def list_runs(request: Request, limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    ctx = _ctx(request)
    reader = TraceReader(ctx.config.runtime.runs_dir)
    return {"runs": reader.list_runs(limit=limit)}


@router.get("/runs/{attempt_id}")
async def get_run(request: Request, attempt_id: str) -> dict[str, Any]:
    ctx = _ctx(request)
    reader = TraceReader(ctx.config.runtime.runs_dir)
    try:
        return reader.get_run(attempt_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run not found: {attempt_id}") from None


@router.websocket("/ws")
async def session_ws(websocket: WebSocket) -> None:
    ctx: AppContext = websocket.app.state.ctx
    await stream_session_events(websocket, ctx.session)
