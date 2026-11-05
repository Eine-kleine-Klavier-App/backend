from collections.abc import Callable, Generator
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from piano_app.application.ports.playback import AudioChunk
from piano_app.domain.score.document.services.playback import PlaybackProjection

from .binding import FluidSynthSession
from .errors import FluidSynthError
from .scheduler import ScheduledSynth, SynthSession, prepare_events


@dataclass(frozen=True, slots=True, kw_only=True)
class FluidSynthRenderer:
    """Draft adapter. Each stream owns a fresh native synth and yields bounded PCM chunks."""

    soundfont: Path
    sample_rate: int = 44100
    chunk_frames: int = 1024
    release_ms: float = 1500
    channels: int = 256
    # FluidSynth's own default is 0.2; 0.8 is 12 dB louder.
    gain: float = 0.8
    library_path: str | None = None
    session_factory: Callable[[], SynthSession] | None = None

    def __post_init__(self) -> None:
        if type(self.sample_rate) is not int or not 8000 <= self.sample_rate <= 96000:
            raise FluidSynthError("Sample rate must be an integer in 8000..96000.")
        if type(self.chunk_frames) is not int or not 1 <= self.chunk_frames <= 65536:
            raise FluidSynthError("Chunk size must be an integer in 1..65536.")
        if not isfinite(self.release_ms) or self.release_ms < 0:
            raise FluidSynthError("Release tail must be finite and nonnegative.")
        if type(self.channels) is not int or not 16 <= self.channels <= 256 or self.channels % 16:
            raise FluidSynthError("Channel count must be a multiple of 16 in 16..256.")
        if not isfinite(self.gain) or not 0 < self.gain <= 10:
            raise FluidSynthError("Gain must be a number in (0, 10].")

    def stream(
        self,
        *,
        projection: PlaybackProjection,
        cancelled: Callable[[], bool] | None = None,
    ) -> Generator[AudioChunk]:
        """Cancellation is polled between chunks/events; close when consumption stops early."""
        if cancelled is not None and cancelled():
            return
        events, total = prepare_events(
            projection=projection, sample_rate=self.sample_rate, release_ms=self.release_ms
        )
        if total == 0 or (cancelled is not None and cancelled()):
            return
        session = self.open_session()
        try:
            session.schedule(events=events, total_frames=total)
            while cancelled is None or not cancelled():
                chunk = session.read()
                if chunk is None:
                    break
                if cancelled is not None and cancelled():
                    return
                yield chunk
        finally:
            session.close()

    def open_session(self) -> ScheduledSynth:
        session = (
            self.session_factory()
            if self.session_factory is not None
            else FluidSynthSession(
                soundfont=self.soundfont,
                sample_rate=self.sample_rate,
                channels=self.channels,
                gain=self.gain,
                library_path=self.library_path,
            )
        )
        return ScheduledSynth(
            session=session,
            sample_rate=self.sample_rate,
            chunk_frames=self.chunk_frames,
            channels=self.channels,
            release_ms=self.release_ms,
        )
