"""Opt-in native checks: set PIANO_TEST_SOUNDFONT and optionally PIANO_FLUIDSYNTH_LIBRARY."""

import os
from array import array
from pathlib import Path

import pytest

from piano_app.adapters.outbound.fluidsynth import FluidSynthError, FluidSynthRenderer
from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    RhythmicSize,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.playback import (
    PlaybackNote,
    PlaybackProjection,
    build_projection,
)

pytestmark = pytest.mark.integration


def preview_chord(
    *, pitches: list[int], velocity: int, duration_ms: float = 650
) -> PlaybackProjection:
    return PlaybackProjection(
        notes=tuple(
            PlaybackNote(
                source_id="",
                pitch=pitch,
                start_ms=0,
                key_release_ms=duration_ms,
                end_ms=duration_ms,
                velocity=velocity,
            )
            for pitch in pitches
        ),
        extent_ms=duration_ms,
    )


@pytest.fixture
def native_renderer() -> FluidSynthRenderer:
    font = os.environ.get("PIANO_TEST_SOUNDFONT")
    if font is None:
        pytest.skip("Set PIANO_TEST_SOUNDFONT to run real FluidSynth checks.")
    return FluidSynthRenderer(
        soundfont=Path(font),
        release_ms=300,
        library_path=os.environ.get("PIANO_FLUIDSYNTH_LIBRARY"),
    )


def test_actual_piano_chord_has_expected_length_and_signal(
    native_renderer: FluidSynthRenderer,
) -> None:
    projection = preview_chord(pitches=[60, 64, 67], velocity=80)
    chunks = list(native_renderer.stream(projection=projection))
    assert sum(c.frame_count for c in chunks) == 41895  # (650 + 300) ms at 44100 Hz
    assert max(abs(s) for s in array("h", b"".join(c.pcm for c in chunks))) > 50
    offset = 0
    for chunk in chunks:
        assert chunk.start_frame == offset
        offset += chunk.frame_count


def test_document_to_projection_to_real_audio(native_renderer: FluidSynthRenderer) -> None:
    document = ScoreDocument.create_fresh(voice_count=1, staff_count=1, measure_count=1)
    leaf = LeafRhythmicContainer.create(
        parent=document.voices[0],
        anchor=document.measures[0].anchors[0],
        size=RhythmicSize(value=DottedRhythmicValue(value=RhythmicValue.HALF), count=1),
    )
    carrier = NoteCarrier.create(owner=leaf)
    for step in (-2, 0, 2):
        Note.create(
            note_carrier=carrier,
            staff=document.staffs[0],
            staff_step=step,
            accidental=Accidental.NATURAL,
        )
    projection = build_projection(document=document)
    chunks = list(native_renderer.stream(projection=projection))
    expected = round(projection.extent_ms * 44100 / 1000) + round(300 * 44100 / 1000)
    assert abs(sum(c.frame_count for c in chunks) - expected) <= 2
    assert max(abs(s) for s in array("h", b"".join(c.pcm for c in chunks))) > 50


def test_many_unisons_include_melodic_channel_nine(native_renderer: FluidSynthRenderer) -> None:
    projection = preview_chord(pitches=[60] * 17, velocity=40, duration_ms=100)
    assert sum(c.frame_count for c in native_renderer.stream(projection=projection)) == 17640


def test_cancel_then_next_native_session_works(native_renderer: FluidSynthRenderer) -> None:
    projection = preview_chord(pitches=[60], velocity=80)
    cancel = False
    stream = native_renderer.stream(projection=projection, cancelled=lambda: cancel)
    next(stream)
    cancel = True
    assert list(stream) == []
    assert len(list(native_renderer.stream(projection=projection))) > 1


def test_invalid_native_font_fails_cleanly(
    tmp_path: Path, native_renderer: FluidSynthRenderer
) -> None:
    path = tmp_path / "invalid.sf2"
    path.write_bytes(b"not a soundfont")
    renderer = FluidSynthRenderer(soundfont=path, library_path=native_renderer.library_path)
    with pytest.raises(FluidSynthError):
        list(renderer.stream(projection=preview_chord(pitches=[60], velocity=80)))


def test_live_noteoff_keeps_audible_native_release_and_accepts_next_chord(
    native_renderer: FluidSynthRenderer,
) -> None:
    live = native_renderer.open_session()
    try:
        live.replace(projection=preview_chord(pitches=[60], velocity=100))
        for _ in range(8):
            assert live.read() is not None
        live.release()
        tail = live.read()
        assert tail is not None
        assert max(abs(s) for s in array("h", tail.pcm)) > 10
        live.replace(projection=preview_chord(pitches=[60, 64, 67], velocity=90))
        chord = live.read()
        assert chord is not None and chord.start_frame > tail.start_frame
        assert max(abs(s) for s in array("h", chord.pcm)) > 10
    finally:
        live.close()
