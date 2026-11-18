from collections.abc import Callable
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.context import Refrain, SustainHold, TempoChange
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import (
    Accidental,
    Articulation,
    DottedRhythmicValue,
    GracePlacement,
    GraceType,
    RhythmicValue,
)
from piano_app.domain.score.document.models.relations import Tie
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import AddGraceNoteIntent
from piano_app.domain.score.document.services.playback import (
    MeasureSounds,
    PlaybackChunks,
    PlaybackNote,
    PlaybackProjection,
    PlayedAnchor,
    Strike,
    build_measure_sounds,
    build_playback_chunks,
    build_projection,
    preview_chord,
)

from ..scene import Score, anchor_at, build_score, note_at, quarters

# A measure of the scene is one whole note; at a quarter = 120 it takes 2000 ms and a quarter
# 500 ms. The notes sit on staff step 0 (E4, MIDI 64) and a new score is piano, velocity 31.
# The playback cut by measure must be the playback of the whole score, only laid out by measure.

_Q: Fraction = Fraction(1, 4)
# where the notes of the scenes below start
_PLAYED: tuple[Fraction, ...] = tuple(Fraction(beat, 4) for beat in range(6))


def _score(*, measures: int) -> Score:
    score: Score = build_score(measure_count=measures)
    start = anchor_at(score=score, at=Fraction(0))
    for context in tuple(start.starting_contexts):
        if isinstance(context, TempoChange):
            context.detach()

    TempoChange.create(
        start=start,
        beat=DottedRhythmicValue(value=RhythmicValue.QUARTER),
        bpm=120,
    )

    return score


def _tied_across_the_barline(*, measures: int = 2) -> Score:
    """Four quarters, the last tied over the barline to the first of two quarters after it."""
    score: Score = _score(measures=measures)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1, beats=(0, 1))
    Tie.create(
        start_note=note_at(score=score, at=Fraction(3, 4)),
        end_note=note_at(score=score, at=Fraction(1)),
    )

    return score


def _every_case() -> Score:
    """The tie over the barline, a pedal over it, an accent and the first two measures repeated,
    with an empty third measure."""
    score: Score = _tied_across_the_barline(measures=3)
    note_at(score=score, at=_Q).note_carrier.set_articulations(
        articulations=frozenset({Articulation.ACCENT})
    )
    SustainHold.create(
        start=anchor_at(score=score, at=Fraction(1, 2)),
        end=anchor_at(score=score, at=Fraction(3, 2)),
    )
    Refrain.create(
        start=anchor_at(score=score, at=Fraction(0)),
        end=anchor_at(score=score, at=Fraction(2)),
        times=2,
    )

    return score


def _note_order(note: PlaybackNote) -> tuple[float, str, int]:
    return note.start_ms, note.source_id, note.pitch


def _anchor_order(anchor: PlayedAnchor) -> tuple[float, str]:
    return anchor.start_ms, anchor.carrier_id


@pytest.mark.unit
def test_the_measures_together_are_the_playback_of_the_whole_score() -> None:
    score: Score = _every_case()

    chunks: PlaybackChunks = build_playback_chunks(document=score.document)
    whole: PlaybackProjection = build_projection(document=score.document)

    assert [measure.measure_id for measure in chunks.measures] == [
        measure.id for measure in score.document.measures
    ]
    notes: list[PlaybackNote] = [note for measure in chunks.measures for note in measure.notes]
    anchors: list[PlayedAnchor] = [
        anchor for measure in chunks.measures for anchor in measure.anchors
    ]
    assert sorted(notes, key=_note_order) == sorted(whole.notes, key=_note_order)
    assert sorted(anchors, key=_anchor_order) == sorted(whole.anchors, key=_anchor_order)
    assert (chunks.extent_ms, chunks.pedals, chunks.segments) == (
        whole.extent_ms,
        whole.pedals,
        whole.segments,
    )


@pytest.mark.unit
def test_a_tie_over_the_barline_sounds_once_in_the_measure_it_starts_in() -> None:
    score: Score = _tied_across_the_barline()
    tied: Note = note_at(score=score, at=Fraction(3, 4))
    continued: Note = note_at(score=score, at=Fraction(1))

    first, second = build_playback_chunks(document=score.document).measures

    (sound,) = [note for note in first.notes if note.source_id == tied.id]
    assert (sound.start_ms, sound.end_ms) == (pytest.approx(1500), pytest.approx(2500))
    assert continued.id not in {note.source_id for note in first.notes + second.notes}
    assert continued.id in {strike.note_id for strike in second.strikes}


@pytest.mark.unit
def test_every_strike_is_the_preview_of_its_note() -> None:
    score: Score = _every_case()

    strikes: dict[str, Strike] = {
        strike.note_id: strike
        for measure in build_playback_chunks(document=score.document).measures
        for strike in measure.strikes
    }

    assert len(strikes) == len(_PLAYED)
    for at in _PLAYED:
        carrier = note_at(score=score, at=at).note_carrier
        for preview in preview_chord(document=score.document, carrier=carrier).notes:
            strike: Strike = strikes[preview.source_id]
            assert (strike.pitch, strike.velocity) == (preview.pitch, preview.velocity)

    assert strikes[note_at(score=score, at=_Q).id].velocity == 56


@pytest.mark.unit
def test_a_measure_with_nothing_to_play_has_an_empty_share() -> None:
    score: Score = _every_case()

    empty = build_playback_chunks(document=score.document).measures[2]

    assert (empty.strikes, empty.notes, empty.anchors) == ((), (), ())


def _with_a_grace_note() -> Score:
    """The scene of every case with a grace note before the second quarter."""
    score: Score = _every_case()
    intent = AddGraceNoteIntent(
        host_carrier_id=note_at(score=score, at=_Q).note_carrier.id,
        placement=GracePlacement.BEFORE,
        grace_type=GraceType.APPOGGIATURA,
        written_value=DottedRhythmicValue(value=RhythmicValue.EIGHTH),
        staff_id=score.staff.id,
        staff_step=2,
        accidental=Accidental.SHARP,
    )
    build_engine().process(
        document=score.document,
        requests=build_compiler().compile(document=score.document, intent=intent),
    )

    return score


@pytest.mark.unit
@pytest.mark.parametrize(
    "scene", [_tied_across_the_barline, _every_case, _with_a_grace_note], ids=lambda s: s.__name__
)
def test_the_sound_of_some_measures_is_their_share_of_the_whole_playback(
    scene: Callable[[], Score],
) -> None:
    score: Score = scene()
    whole: dict[str, MeasureSounds] = {
        share.measure_id: share for share in build_playback_chunks(document=score.document).measures
    }
    ids: list[str] = [measure.id for measure in score.document.measures]

    choices: list[list[str]] = [[measure_id] for measure_id in ids] + [ids[:2], [ids[0], ids[-1]]]
    for chosen in choices:
        assert build_measure_sounds(document=score.document, measure_ids=chosen) == tuple(
            whole[measure_id] for measure_id in ids if measure_id in chosen
        ), chosen
