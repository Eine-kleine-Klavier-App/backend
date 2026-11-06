"""Draft server synthesis port. Transport and request lifecycle remain application concerns."""

from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Literal, Protocol

from piano_app.domain.score.document.services.playback import PlaybackProjection


@dataclass(frozen=True, slots=True, kw_only=True)
class AudioChunk:
    """Interleaved stereo signed 16-bit little-endian PCM, with an absolute frame offset."""

    pcm: bytes
    start_frame: int
    sample_rate: int
    channels: Literal[2] = 2
    sample_format: Literal["s16le"] = "s16le"

    @property
    def frame_count(self) -> int:
        return len(self.pcm) // 4


class PlaybackRenderer(Protocol):
    def stream(
        self,
        *,
        projection: PlaybackProjection,
        cancelled: Callable[[], bool] | None = None,
    ) -> Generator[AudioChunk]:
        """Consume incrementally; close the generator when abandoning a stream."""
        ...


class PlaybackSession(Protocol):
    """One live synthesizer: attacks replace each other while the release tails stay."""

    @property
    def sample_rate(self) -> int: ...
    def replace(self, *, projection: PlaybackProjection) -> None: ...
    def release(self) -> None: ...
    def read(self, *, max_frames: int | None = None) -> AudioChunk | None: ...
    def close(self) -> None: ...


class LivePlaybackRenderer(PlaybackRenderer, Protocol):
    def open_session(self) -> PlaybackSession: ...
