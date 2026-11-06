"""Authenticated live audition with bounded PCM credit, independent of HTTP score rendering."""

import asyncio
import struct
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Annotated, Literal

import anyio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from piano_app.application.errors import (
    DraftNotFoundError,
    InvalidAccessTokenError,
    PlaybackCarrierNotFoundError,
    PlaybackRejectedError,
)
from piano_app.application.use_cases.auth import AuthService
from piano_app.application.use_cases.score.playback.preview_session import (
    PreviewSession,
    PreviewSessionService,
)

from .requests import PreviewRequest


class Authentication(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["auth"]
    token: str = Field(min_length=1, max_length=8192)


class PreviewCommand(PreviewRequest):
    model_config = ConfigDict(extra="forbid")
    type: Literal["preview"]
    sequence: int = Field(gt=0, le=2**53 - 1, strict=True)


class ReleaseCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["release"]
    sequence: int = Field(gt=0, le=2**53 - 1, strict=True)


class CreditCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["ack"]
    frames: int = Field(ge=0, le=2**53 - 1, strict=True)


_COMMAND: TypeAdapter[PreviewCommand | ReleaseCommand | CreditCommand] = TypeAdapter(
    Annotated[PreviewCommand | ReleaseCommand | CreditCommand, Field(discriminator="type")]
)


def build_preview_socket_router(
    *, service: PreviewSessionService, auth: AuthService, allowed_origins: tuple[str, ...]
) -> APIRouter:
    router = APIRouter()

    @router.websocket("/drafts/{draft_id}/playback/preview/live")
    async def preview_socket(websocket: WebSocket, draft_id: str) -> None:
        origin = websocket.headers.get("origin")
        if origin is None or origin not in allowed_origins:
            await websocket.close(code=4403)
            return
        await websocket.accept()
        session: PreviewSession | None = None
        tasks: list[asyncio.Task[None]] = []
        send_lock = asyncio.Lock()

        async def send(payload: dict[str, object]) -> None:
            async with send_lock:
                await websocket.send_json(payload)

        try:
            raw_auth = await asyncio.wait_for(websocket.receive_text(), timeout=5)
            credentials = Authentication.model_validate_json(raw_auth)
            viewer_id = auth.authenticate_access_token(token=credentials.token)
            session = await service.open(draft_id=draft_id, viewer_id=viewer_id)
            await send({"type": "ready"})
            await run_session(
                websocket=websocket,
                session=session,
                auth=auth,
                token=credentials.token,
                send=send,
                send_lock=send_lock,
                tasks=tasks,
            )
        except InvalidAccessTokenError:
            with suppress(RuntimeError, WebSocketDisconnect):
                await websocket.close(code=4401)
        except DraftNotFoundError, PlaybackCarrierNotFoundError:
            with suppress(RuntimeError, WebSocketDisconnect):
                await websocket.close(code=4404)
        except ValidationError, ValueError:
            with suppress(RuntimeError, WebSocketDisconnect):
                await websocket.close(code=4400)
        except TimeoutError:
            with suppress(RuntimeError, WebSocketDisconnect):
                await websocket.close(code=1000)
        except WebSocketDisconnect:
            pass
        except asyncio.CancelledError:
            pass
        except Exception:
            # No native errors, token contents or document data cross this boundary.
            with suppress(RuntimeError, WebSocketDisconnect):
                await send({"type": "error", "status": 503, "detail": "Live preview failed."})
                await websocket.close(code=1011)
        finally:
            with anyio.CancelScope(shield=True):
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                if session is not None:
                    await session.close()

    return router


# Kept separate so a socket owns exactly these three bounded activities.
async def run_session(
    *,
    websocket: WebSocket,
    session: PreviewSession,
    auth: AuthService,
    token: str,
    send: Callable[[dict[str, object]], Awaitable[None]],
    send_lock: asyncio.Lock,
    tasks: list[asyncio.Task[None]],
) -> None:
    send_json = send
    commands: asyncio.Queue[PreviewCommand | ReleaseCommand] = asyncio.Queue(maxsize=1)
    wake = asyncio.Event()
    sent = 0
    consumed = 0
    applied = 0
    formatted = False

    async def receive_commands() -> None:
        nonlocal consumed
        while True:
            raw = await websocket.receive_text()
            auth.authenticate_access_token(token=token)
            if len(raw) > 16384:
                raise ValueError("Command too large.")
            try:
                command = _COMMAND.validate_json(raw)
            except ValidationError:
                await send_json({"type": "error", "status": 422, "detail": "Invalid command."})
                continue
            if isinstance(command, CreditCommand):
                if not consumed <= command.frames <= sent:
                    raise ValueError("Invalid PCM credit.")
                consumed = command.frames
                wake.set()
                continue
            if not session.supersede(sequence=command.sequence):
                continue
            if commands.full():
                commands.get_nowait()
            commands.put_nowait(command)

    async def apply_commands() -> None:
        nonlocal formatted, applied
        while True:
            command = await commands.get()
            try:
                version: int | None = None
                if isinstance(command, PreviewCommand):
                    version = await session.replace(
                        sequence=command.sequence,
                        carrier_id=command.carrier_id,
                        note_ids=None if command.note_ids is None else tuple(command.note_ids),
                    )
                    if version is None:
                        continue
                else:
                    await session.release(sequence=command.sequence)
                if session.sample_rate is not None and not formatted:
                    await send_json(
                        {
                            "type": "format",
                            "sample_rate": session.sample_rate,
                            "channels": 2,
                            "format": "s16le",
                            "packet_sequence": "u64le",
                            "max_buffer_frames": max(1, session.sample_rate * 40 // 1000),
                        }
                    )
                    formatted = True
                await send_json(
                    {"type": "accepted", "sequence": command.sequence, "version": version}
                )
                applied = command.sequence
                wake.set()
            except (PlaybackRejectedError, PlaybackCarrierNotFoundError) as error:
                status = 404 if isinstance(error, PlaybackCarrierNotFoundError) else 422
                await send_json(
                    {
                        "type": "error",
                        "status": status,
                        "sequence": command.sequence,
                        "detail": str(error),
                    }
                )

    async def produce_audio() -> None:
        nonlocal sent
        idle: tuple[int, int] | None = None
        while True:
            wake.clear()
            rate = session.sample_rate
            credit = 0 if rate is None else max(1, rate * 40 // 1000) - (sent - consumed)
            if not formatted or rate is None or credit <= 0:
                await asyncio.wait_for(wake.wait(), timeout=60)
                continue
            rendered = await session.read(max_frames=min(max(1, rate // 100), credit))
            if rendered is None:
                marker = applied, sent
                if idle != marker:
                    await send_json({"type": "idle", "sequence": applied, "frames": sent})
                    idle = marker
                await asyncio.wait_for(wake.wait(), timeout=60)
                continue
            idle = None
            rendered_sequence, chunk = rendered
            async with send_lock:
                # Publish credit before awaiting the send: a fast client may ack immediately.
                sent += chunk.frame_count
                await websocket.send_bytes(struct.pack("<Q", rendered_sequence) + chunk.pcm)

    tasks.extend(
        asyncio.create_task(operation())
        for operation in (receive_commands, apply_commands, produce_audio)
    )
    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in done:
        task.result()
