"""Shared offline/live event scheduling. All methods belong to one synthesis worker."""

from collections.abc import Sequence
from dataclasses import dataclass
from heapq import heappop, heappush
from math import floor, isfinite
from typing import Protocol

from piano_app.application.ports.playback import AudioChunk
from piano_app.domain.score.document.services.playback import PlaybackProjection

from .errors import FluidSynthError


class SynthSession(Protocol):
    def note_on(self, *, channel: int, pitch: int, velocity: int) -> None: ...
    def note_off(self, *, channel: int, pitch: int) -> None: ...
    def read(self, *, frames: int) -> bytes: ...
    def close(self) -> None: ...


def frame_at(*, milliseconds: float, sample_rate: int) -> int:
    frames = milliseconds * sample_rate / 1000
    if not isfinite(frames):
        raise FluidSynthError("Audio duration exceeds the supported numeric range.")
    return floor(frames + 0.5)


@dataclass(frozen=True, slots=True)
class SynthEvent:
    frame: int
    on: bool
    index: int
    pitch: int
    velocity: int


def prepare_events(
    *, projection: PlaybackProjection, sample_rate: int, release_ms: float
) -> tuple[list[SynthEvent], int]:
    events: list[SynthEvent] = []
    for index, note in enumerate(projection.notes):
        if type(note.pitch) is not int or not 0 <= note.pitch <= 127:
            raise FluidSynthError("Pitch lies outside FluidSynth's MIDI range.")
        start = frame_at(milliseconds=note.start_ms, sample_rate=sample_rate)
        end = max(start + 1, frame_at(milliseconds=note.end_ms, sample_rate=sample_rate))
        events.extend(
            (
                SynthEvent(start, True, index, note.pitch, note.velocity),
                SynthEvent(end, False, index, note.pitch, note.velocity),
            )
        )
    total = max(
        frame_at(milliseconds=projection.extent_ms, sample_rate=sample_rate),
        max((event.frame for event in events), default=0),
    )
    if events:
        total += frame_at(milliseconds=release_ms, sample_rate=sample_rate)
    return events, total


class ScheduledSynth:
    """One native synth; replacing attacks leaves its existing release voices alive."""

    def __init__(
        self,
        *,
        session: SynthSession,
        sample_rate: int,
        chunk_frames: int,
        channels: int,
        release_ms: float,
    ) -> None:
        self.sample_rate = sample_rate
        self._session = session
        self._chunk_frames = chunk_frames
        self._channels = channels
        self._release_frames = frame_at(milliseconds=release_ms, sample_rate=sample_rate)
        self._release_ms = release_ms
        self._position = 0
        self._end = 0
        self._next_index = 0
        self._events: list[tuple[int, bool, int, int, int]] = []
        self._active: dict[int, tuple[int, int]] = {}
        self._releasing: dict[tuple[int, int], int] = {}
        self._closed = False

    def replace(self, *, projection: PlaybackProjection) -> None:
        events, total = prepare_events(
            projection=projection, sample_rate=self.sample_rate, release_ms=self._release_ms
        )
        self.release()
        self.schedule(events=events, total_frames=total)

    def schedule(self, *, events: Sequence[SynthEvent], total_frames: int) -> None:
        self._require_open()
        offset = self._next_index
        for event in events:
            heappush(
                self._events,
                (
                    self._position + event.frame,
                    event.on,
                    offset + event.index,
                    event.pitch,
                    event.velocity,
                ),
            )
        self._next_index += max((event.index for event in events), default=-1) + 1
        self._end = max(self._end, self._position + total_frames)

    def release(self) -> None:
        self._require_open()
        self._events.clear()
        if self._active:
            self._end = self._position + self._release_frames
        else:
            # No attacks remain: retain an existing tail, but discard future silence.
            self._end = max(self._releasing.values(), default=self._position)
        for channel, pitch in self._active.values():
            self._session.note_off(channel=channel, pitch=pitch)
            self._releasing[(pitch, channel)] = self._position + self._release_frames
        self._active.clear()

    def read(self, *, max_frames: int | None = None) -> AudioChunk | None:
        self._require_open()
        if max_frames is not None and (type(max_frames) is not int or max_frames < 1):
            raise FluidSynthError("Audio reads require positive frame counts.")
        self._releasing = {key: end for key, end in self._releasing.items() if end > self._position}
        while self._events and self._events[0][0] <= self._position:
            _, on, index, pitch, velocity = heappop(self._events)
            if on:
                used = {channel for channel, key in self._active.values() if key == pitch}
                used.update(
                    channel
                    for (key, channel), end in self._releasing.items()
                    if key == pitch and end > self._position
                )
                channel = next((c for c in range(self._channels) if c not in used), None)
                if channel is None:
                    raise FluidSynthError("Too many overlapping attacks of the same pitch.")
                self._session.note_on(channel=channel, pitch=pitch, velocity=velocity)
                self._active[index] = channel, pitch
            else:
                channel, _ = self._active.pop(index)
                self._session.note_off(channel=channel, pitch=pitch)
                self._releasing[(pitch, channel)] = self._position + self._release_frames
        if self._position >= self._end:
            return None
        boundary = self._events[0][0] if self._events else self._end
        count = min(
            self._chunk_frames,
            max_frames if max_frames is not None else self._chunk_frames,
            boundary - self._position,
            self._end - self._position,
        )
        pcm = self._session.read(frames=count)
        if len(pcm) != count * 4:
            raise FluidSynthError("Synthesizer returned an invalid PCM chunk size.")
        chunk = AudioChunk(pcm=pcm, start_frame=self._position, sample_rate=self.sample_rate)
        self._position += count
        return chunk

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._session.close()

    def _require_open(self) -> None:
        if self._closed:
            raise FluidSynthError("Synthesizer session is closed.")
