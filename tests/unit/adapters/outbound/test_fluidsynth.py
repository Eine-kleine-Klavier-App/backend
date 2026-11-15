from pathlib import Path
from unittest.mock import Mock

import pytest

from piano_app.adapters.outbound.fluidsynth import FluidSynthError, FluidSynthRenderer
from piano_app.adapters.outbound.fluidsynth.binding import FluidSynthSession
from piano_app.domain.score.document.services.playback import PlaybackNote, PlaybackProjection


class FakeSession:
    def __init__(self) -> None:
        self.position = 0
        self.events: list[tuple[str, int, int, int, int]] = []
        self.closed = False
        self.fail_read = False

    def note_on(self, *, channel: int, pitch: int, velocity: int) -> None:
        self.events.append(("on", self.position, channel, pitch, velocity))

    def note_off(self, *, channel: int, pitch: int) -> None:
        self.events.append(("off", self.position, channel, pitch, 0))

    def read(self, *, frames: int) -> bytes:
        if self.fail_read:
            raise FluidSynthError("read failed")
        self.position += frames
        return bytes(frames * 4)

    def close(self) -> None:
        self.closed = True


def renderer(session: FakeSession, *, tail: float = 0) -> FluidSynthRenderer:
    return FluidSynthRenderer(
        soundfont=Path("unused.sf2"),
        sample_rate=8000,
        chunk_frames=100,
        release_ms=tail,
        session_factory=lambda: session,
    )


def sound(start: float, duration: float, pitch: int = 60, velocity: int = 80) -> PlaybackNote:
    return PlaybackNote(
        source_id="",
        pitch=pitch,
        start_ms=start,
        key_release_ms=start + duration,
        end_ms=start + duration,
        velocity=velocity,
    )


def preview_chord(
    *, pitches: list[int], velocity: int, duration_ms: float = 650
) -> PlaybackProjection:
    return PlaybackProjection(
        notes=tuple(sound(0, duration_ms, pitch, velocity) for pitch in pitches),
        extent_ms=duration_ms,
    )


def test_event_timing_unisons_and_off_before_on() -> None:
    session = FakeSession()
    projection = PlaybackProjection(
        notes=(sound(0, 100), sound(50, 100), sound(100, 100)), extent_ms=250
    )
    chunks = list(renderer(session).stream(projection=projection))
    assert session.events == [
        ("on", 0, 0, 60, 80),
        ("on", 400, 1, 60, 80),
        ("off", 800, 0, 60, 0),
        ("on", 800, 0, 60, 80),
        ("off", 1200, 1, 60, 0),
        ("off", 1600, 0, 60, 0),
    ]
    assert sum(c.frame_count for c in chunks) == 2000
    assert all(c.frame_count <= 100 for c in chunks)
    assert [c.start_frame for c in chunks] == list(range(0, 2000, 100))
    assert session.closed


def test_chunks_include_initial_silence_and_release_tail() -> None:
    session = FakeSession()
    chunks = list(
        renderer(session, tail=50).stream(
            projection=PlaybackProjection(notes=(sound(50, 50),), extent_ms=150)
        )
    )
    assert session.events[0][1] == 400
    assert sum(c.frame_count for c in chunks) == 1600


def test_tiny_sound_keeps_one_frame_and_noteoff() -> None:
    session = FakeSession()
    chunks = list(
        renderer(session).stream(
            projection=PlaybackProjection(notes=(sound(0, 0.001),), extent_ms=0.001)
        )
    )
    assert sum(c.frame_count for c in chunks) == 1
    assert [e[0] for e in session.events] == ["on", "off"]
    assert session.closed


def test_cancel_and_explicit_close_release_session() -> None:
    session = FakeSession()
    cancelled = False
    stream = renderer(session).stream(
        projection=preview_chord(pitches=[60], velocity=80),
        cancelled=lambda: cancelled,
    )
    next(stream)
    cancelled = True
    assert list(stream) == []
    assert session.closed
    another = FakeSession()
    stream = renderer(another).stream(projection=preview_chord(pitches=[60], velocity=80))
    next(stream)
    stream.close()
    assert another.closed


def test_pre_cancel_and_zero_extent_allocate_nothing() -> None:
    factory = Mock(side_effect=AssertionError("must not allocate"))
    adapter = FluidSynthRenderer(soundfont=Path("unused"), session_factory=factory)
    assert (
        list(
            adapter.stream(
                projection=PlaybackProjection(notes=(), extent_ms=100), cancelled=lambda: True
            )
        )
        == []
    )
    assert list(adapter.stream(projection=PlaybackProjection(notes=(), extent_ms=0))) == []
    factory.assert_not_called()


def test_read_failure_and_invalid_pcm_cleanup() -> None:
    session = FakeSession()
    session.fail_read = True
    with pytest.raises(FluidSynthError, match="read failed"):
        list(
            renderer(session).stream(
                projection=PlaybackProjection(notes=(sound(0, 100),), extent_ms=100)
            )
        )
    assert session.closed

    class BadPCM(FakeSession):
        def read(self, *, frames: int) -> bytes:
            return b""

    broken = BadPCM()
    with pytest.raises(FluidSynthError, match="PCM"):
        list(renderer(broken).stream(projection=PlaybackProjection(notes=(), extent_ms=100)))
    assert broken.closed


def test_pitch_refusal_happens_before_session_allocation() -> None:
    factory = Mock(side_effect=AssertionError("must not allocate"))
    adapter = FluidSynthRenderer(soundfont=Path("unused"), session_factory=factory)
    with pytest.raises(FluidSynthError, match="MIDI range"):
        list(
            adapter.stream(
                projection=PlaybackProjection(notes=(sound(0, 100, 128),), extent_ms=100)
            )
        )
    factory.assert_not_called()


def test_channel_exhaustion_is_explicit_and_cleans_up() -> None:
    session = FakeSession()
    adapter = FluidSynthRenderer(
        soundfont=Path("unused"), channels=16, session_factory=lambda: session
    )
    with pytest.raises(FluidSynthError, match="overlapping"):
        list(
            adapter.stream(
                projection=PlaybackProjection(notes=(sound(0, 100),) * 17, extent_ms=100)
            )
        )
    assert session.closed


def test_separate_streams_have_separate_sessions() -> None:
    sessions: list[FakeSession] = []

    def factory() -> FakeSession:
        session = FakeSession()
        sessions.append(session)
        return session

    adapter = FluidSynthRenderer(soundfont=Path("unused"), release_ms=0, session_factory=factory)
    for _ in range(2):
        list(adapter.stream(projection=PlaybackProjection(notes=(sound(0, 100),), extent_ms=100)))
    assert len(sessions) == 2 and all(s.closed for s in sessions)
    assert sessions[0].events == sessions[1].events


def test_native_allocation_failure_frees_partial_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    font = tmp_path / "font.sf2"
    font.touch()
    library = Mock()
    library.new_fluid_settings.return_value = 11
    library.fluid_settings_setnum.return_value = 0
    library.fluid_settings_setint.return_value = 0
    library.new_fluid_synth.return_value = 22
    library.fluid_synth_sfload.return_value = -1
    monkeypatch.setattr(
        "piano_app.adapters.outbound.fluidsynth.binding.c.CDLL", lambda path: library
    )
    with pytest.raises(FluidSynthError):
        FluidSynthSession(
            soundfont=font, sample_rate=44100, channels=16, gain=0.8, library_path="test"
        )
    library.delete_fluid_synth.assert_called_once_with(22)
    library.delete_fluid_settings.assert_called_once_with(11)


def test_missing_font_is_clear(tmp_path: Path) -> None:
    with pytest.raises(FluidSynthError, match="SoundFont does not exist"):
        FluidSynthSession(
            soundfont=tmp_path / "missing.sf2", sample_rate=44100, channels=16, gain=0.8
        )


def test_cancellation_during_read_discards_chunk_and_closes() -> None:
    cancel = False

    class CancellingSession(FakeSession):
        def read(self, *, frames: int) -> bytes:
            nonlocal cancel
            cancel = True
            return super().read(frames=frames)

    session = CancellingSession()
    assert (
        list(
            renderer(session).stream(
                projection=PlaybackProjection(notes=(sound(0, 100),), extent_ms=100),
                cancelled=lambda: cancel,
            )
        )
        == []
    )
    assert session.closed


def test_note_on_failure_closes_session() -> None:
    class BrokenSession(FakeSession):
        def note_on(self, *, channel: int, pitch: int, velocity: int) -> None:
            raise FluidSynthError("note failed")

    session = BrokenSession()
    with pytest.raises(FluidSynthError, match="note failed"):
        list(
            renderer(session).stream(
                projection=PlaybackProjection(notes=(sound(0, 100),), extent_ms=100)
            )
        )
    assert session.closed


def test_native_close_is_idempotent_and_channel_nine_is_melodic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    font = tmp_path / "font.sf2"
    font.touch()
    library = Mock()
    for name in (
        "fluid_settings_setnum",
        "fluid_settings_setint",
        "fluid_synth_set_channel_type",
        "fluid_synth_program_select",
        "fluid_synth_noteon",
    ):
        getattr(library, name).return_value = 0
    library.new_fluid_settings.return_value = 11
    library.new_fluid_synth.return_value = 22
    library.fluid_synth_sfload.return_value = 1
    monkeypatch.setattr(
        "piano_app.adapters.outbound.fluidsynth.binding.c.CDLL", lambda path: library
    )
    session = FluidSynthSession(
        soundfont=font, sample_rate=44100, channels=16, gain=0.8, library_path="test"
    )
    session.note_on(channel=9, pitch=60, velocity=80)
    library.fluid_synth_set_channel_type.assert_called_once_with(22, 9, 0)
    library.fluid_synth_program_select.assert_called_once_with(22, 9, 1, 0, 0)
    session.close()
    session.close()
    library.delete_fluid_synth.assert_called_once_with(22)
    library.delete_fluid_settings.assert_called_once_with(11)
    with pytest.raises(FluidSynthError, match="closed"):
        session.note_on(channel=0, pitch=60, velocity=80)


def test_live_replacement_releases_old_keys_but_keeps_the_native_synth_and_tail() -> None:
    native = FakeSession()
    live = renderer(native, tail=100).open_session()
    live.replace(projection=preview_chord(pitches=[60], velocity=80))
    first = live.read(max_frames=80)
    assert first is not None and first.start_frame == 0
    live.replace(projection=preview_chord(pitches=[64], velocity=90))
    second = live.read(max_frames=80)
    assert second is not None and second.start_frame == 80
    assert native.events[:3] == [("on", 0, 0, 60, 80), ("off", 80, 0, 60, 0), ("on", 80, 0, 64, 90)]
    assert not native.closed
    live.release()
    while live.read() is not None:
        pass
    assert native.position == 960  # 20 ms rendered + 100 ms release
    assert [(e[0], e[3]) for e in native.events] == [
        ("on", 60),
        ("off", 60),
        ("on", 64),
        ("off", 64),
    ]
    live.close()
    live.close()
    assert native.closed


def test_live_repeated_pitch_does_not_reuse_a_channel_with_a_sounding_release() -> None:
    native = FakeSession()
    live = renderer(native, tail=100).open_session()
    projection = preview_chord(pitches=[60], velocity=80)
    for _ in range(3):
        live.replace(projection=projection)
        live.read(max_frames=80)
    assert [e[2] for e in native.events if e[0] == "on"] == [0, 1, 2]
    live.release()
    while live.read() is not None:
        pass
    live.replace(projection=projection)
    live.read(max_frames=80)
    assert native.events[-1][2] == 0
    live.close()


def test_invalid_live_replacement_does_not_release_the_valid_previous_target() -> None:
    native = FakeSession()
    live = renderer(native).open_session()
    live.replace(projection=preview_chord(pitches=[60], velocity=80))
    live.read()
    events = list(native.events)
    with pytest.raises(FluidSynthError):
        live.replace(projection=PlaybackProjection(notes=(sound(0, 100, 128),), extent_ms=100))
    assert native.events == events
    live.close()


def test_the_native_synth_gets_the_configured_gain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    font = tmp_path / "font.sf2"
    font.touch()
    library = Mock()
    for name in ("fluid_settings_setnum", "fluid_settings_setint"):
        getattr(library, name).return_value = 0
    library.new_fluid_settings.return_value = 11
    library.new_fluid_synth.return_value = 22
    library.fluid_synth_sfload.return_value = 1
    monkeypatch.setattr(
        "piano_app.adapters.outbound.fluidsynth.binding.c.CDLL", lambda path: library
    )
    FluidSynthSession(soundfont=font, sample_rate=44100, channels=16, gain=0.8, library_path="test")
    library.fluid_settings_setnum.assert_any_call(11, b"synth.gain", 0.8)


@pytest.mark.parametrize("gain", [0.0, -0.1, 10.5, float("nan"), float("inf")])
def test_a_gain_outside_the_synth_range_is_refused(gain: float) -> None:
    with pytest.raises(FluidSynthError, match="Gain"):
        FluidSynthRenderer(soundfont=Path("unused"), gain=gain)
