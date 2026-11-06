import json
import struct
from collections.abc import AsyncIterator, Generator
from threading import Event
from typing import Literal

import anyio
from starlette.responses import Response, StreamingResponse
from starlette.types import Receive, Scope, Send

from piano_app.application.errors import PlaybackUnavailableError
from piano_app.application.ports.playback import AudioChunk
from piano_app.application.use_cases.score.playback import PreparedPlayback
from piano_app.domain.score.document.services.playback import PlaybackProjection

AUDIO_HEADERS: tuple[str, ...] = (
    "X-Audio-Sample-Rate",
    "X-Audio-Channels",
    "X-Audio-Format",
    "X-Draft-Version",
    "X-Score-Version",
    "X-Playback-Extent-Ms",
)


def _next_chunk(stream: Generator[AudioChunk]) -> AudioChunk | None:
    return next(stream, None)


async def _close(*, stream: Generator[AudioChunk], cancelled: Event) -> None:
    cancelled.set()
    # Worker reads are non-abandoning; they finish before the generator is closed.
    with anyio.CancelScope(shield=True):
        await anyio.to_thread.run_sync(stream.close)


class PlaybackResponse(StreamingResponse):
    def __init__(
        self,
        *,
        stream: Generator[AudioChunk],
        first: AudioChunk,
        cancelled: Event,
        headers: dict[str, str],
        prefix: bytes = b"",
    ) -> None:
        self._stream = stream
        self._cancelled = cancelled

        async def body() -> AsyncIterator[bytes]:
            if prefix:
                yield prefix
            yield first.pcm
            while True:
                chunk = await anyio.to_thread.run_sync(_next_chunk, stream)
                if chunk is None:
                    break
                yield chunk.pcm

        super().__init__(
            body(),
            media_type="application/vnd.piano.playback" if prefix else "application/octet-stream",
            headers=headers,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await _close(stream=self._stream, cancelled=self._cancelled)


def playback_map_payload(*, projection: PlaybackProjection, version: int) -> dict[str, object]:
    """The map of the playback for the frontend. ``notes`` are the notes in the order they
    sound; ``anchors`` the leaves (notes, chords, rests) as they are played, for lighting them;
    ``segments`` the stretches of the score in the order they are played, each with moments
    from which the time of a place of the score is read. With repeats a place of the score is
    played more than once, so the map is by time, with a segment for each pass."""
    return {
        "version": version,
        "extent_ms": projection.extent_ms,
        "notes": [
            {
                "source_id": note.source_id,
                "pitch": note.pitch,
                "start_ms": note.start_ms,
                "key_release_ms": note.key_release_ms,
                "end_ms": note.end_ms,
                "velocity": note.velocity,
            }
            for note in projection.notes
        ],
        "pedals": [{"down_ms": pedal.down_ms, "up_ms": pedal.up_ms} for pedal in projection.pedals],
        "anchors": [
            {
                "carrier_id": anchor.carrier_id,
                "start_ms": anchor.start_ms,
                "end_ms": anchor.end_ms,
            }
            for anchor in projection.anchors
        ],
        "segments": [
            {
                "start": {
                    "numerator": segment.start.numerator,
                    "denominator": segment.start.denominator,
                },
                "end": {"numerator": segment.end.numerator, "denominator": segment.end.denominator},
                "start_ms": segment.start_ms,
                "end_ms": segment.end_ms,
                "moments": [
                    {
                        "position": {
                            "numerator": moment.position.numerator,
                            "denominator": moment.position.denominator,
                        },
                        "time_ms": moment.time_ms,
                    }
                    for moment in segment.moments
                ],
            }
            for segment in projection.segments
        ],
    }


def preview_map_payload(
    *, projections: dict[str, PlaybackProjection], version: int
) -> dict[str, object]:
    return {
        "version": version,
        "carriers": [
            {
                "carrier_id": carrier_id,
                "notes": [
                    {
                        "source_id": note.source_id,
                        "pitch": note.pitch,
                        "velocity": note.velocity,
                        "duration_ms": note.key_release_ms - note.start_ms,
                    }
                    for note in projection.notes
                ],
            }
            for carrier_id, projection in projections.items()
        ],
    }


async def playback_response(
    *,
    prepared: PreparedPlayback,
    include_map: bool = False,
    version_header: Literal["X-Draft-Version", "X-Score-Version"] = "X-Draft-Version",
) -> Response:
    cancelled = Event()
    stream = prepared.renderer.stream(projection=prepared.projection, cancelled=cancelled.is_set)
    try:
        first = await anyio.to_thread.run_sync(_next_chunk, stream)
    except BaseException as error:
        await _close(stream=stream, cancelled=cancelled)
        if isinstance(error, RuntimeError):
            raise PlaybackUnavailableError("Server synthesis could not start.") from error
        raise
    headers = {
        version_header: str(prepared.version),
        "X-Playback-Extent-Ms": str(prepared.projection.extent_ms),
        "Cache-Control": "no-store",
    }
    if first is None:
        await _close(stream=stream, cancelled=cancelled)
        return Response(status_code=204, headers=headers)
    headers.update(
        {
            "X-Audio-Sample-Rate": str(first.sample_rate),
            "X-Audio-Channels": str(first.channels),
            "X-Audio-Format": first.sample_format,
        }
    )
    prefix = b""
    if include_map:
        metadata = json.dumps(
            playback_map_payload(projection=prepared.projection, version=prepared.version),
            separators=(",", ":"),
        ).encode()
        prefix = struct.pack("<I", len(metadata)) + metadata
    return PlaybackResponse(
        stream=stream, first=first, cancelled=cancelled, headers=headers, prefix=prefix
    )
