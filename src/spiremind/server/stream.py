"""WebSocket event streaming bridge for live AgentSession updates."""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import WebSocket, WebSocketDisconnect

from spiremind.agent.session import AgentSession


async def stream_session_events(websocket: WebSocket, session: AgentSession) -> None:
    """Accept a WebSocket client, push full initial snapshot, and stream live events."""
    await websocket.accept()
    queue = session.subscribe()
    try:
        await websocket.send_json({"type": "session_snapshot", "data": session.snapshot()})

        async def _reader() -> None:
            while True:
                msg = await websocket.receive_text()
                if msg == "ping":
                    await websocket.send_json({"type": "pong", "data": {"status": session.status}})
                elif msg == "snapshot":
                    await websocket.send_json({"type": "session_snapshot", "data": session.snapshot()})

        reader_task = asyncio.create_task(_reader())
        try:
            while True:
                get_task = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait(
                    {reader_task, get_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if reader_task in done:
                    get_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await get_task
                    exc = reader_task.exception()
                    if exc is not None:
                        raise exc
                    break
                event = get_task.result()
                await websocket.send_json(event)
        finally:
            if not reader_task.done():
                reader_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect):
                    await reader_task
    except WebSocketDisconnect:
        pass
    finally:
        session.unsubscribe(queue)
