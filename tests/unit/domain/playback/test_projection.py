from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.context import Refrain, SustainHold, TempoChange
from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import (
    Articulation,
    DottedRhythmicValue,
    RhythmicValue,
)
from piano_app.domain.score.document.models.relations import Tie
from piano_app.domain.score.document.services.playback import (
    PlaybackProjection,
    build_projection,
    preview_chord,
)

from ..scene import Score, anchor_at, build_score, insert_note, note_at, quarters

# A measure of the scene is one whole note; at a quarter = 120 it takes 2000 ms and a quarter
# 500 ms. The notes sit on staff step 0 (E4, MIDI 64) and a new score is piano, velocity 31.

_Q: Fraction = Fraction(1, 4)


@pytest.mark.unit
def test_pedal_keeps_key_release_separate_and_survives_a_fragment_cut() -> None:
    scene = _score()
    quarters(score=scene, measure=0, beats=(0,))
    note_at(score=scene, at=Fraction(0)).note_carrier.set_articulations(
        articulations=frozenset({Articulation.STACCATO})
    )
    SustainHold.create(
        start=anchor_at(score=scene, at=Fraction(0)),
        end=anchor_at(score=scene, at=Fraction(1)),
    )
    full = build_projection(document=scene.document)
    assert full.notes[0].key_release_ms == pytest.approx(250)
    assert full.notes[0].end_ms == pytest.approx(2000)
    assert [(p.down_ms, p.up_ms) for p in full.pedals] == [(0, 2000)]

    cut = build_projection(document=scene.document, start=Fraction(1, 4))
    assert cut.notes[0].key_release_ms == 0
    assert cut.notes[0].end_ms == pytest.approx(1500)
    assert [(p.down_ms, p.up_ms) for p in cut.pedals] == [(0, 1500)]

    after = build_projection(document=scene.document, start=Fraction(1))
    assert after.pedals == ()


@pytest.mark.unit
def test_projection_repeats_pedal_actions_in_playback_time() -> None:
    scene = _score(measures=3)
    SustainHold.create(
        start=anchor_at(score=scene, at=Fraction(3, 2)),
        end=anchor_at(score=scene, at=Fraction(5, 2)),
    )
    Refrain.create(
        start=anchor_at(score=scene, at=Fraction(0)),
        end=anchor_at(score=scene, at=Fraction(2)),
        times=2,
    )
    projection = build_projection(document=scene.document)
    assert [(p.down_ms, p.up_ms) for p in projection.pedals] == [(3000, 4000), (7000, 9000)]


def _score(*, measures: int = 2) -> Score:
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


def _shapes(*, projection: PlaybackProjection) -> list[tuple[int, float, float, int]]:
    return [(note.pitch, note.start_ms, note.end_ms, note.velocity) for note in projection.notes]


@pytest.mark.unit
def test_a_score_is_played_as_notes_with_their_time_and_velocity() -> None:
    score: Score = _score()
    quarters(score=score, measure=0, beats=(0, 1))

    projection: PlaybackProjection = build_projection(document=score.document)

    assert _shapes(projection=projection) == [
        (64, pytest.approx(0), pytest.approx(500), 31),
        (64, pytest.approx(500), pytest.approx(1000), 31),
    ]
    assert projection.extent_ms == pytest.approx(4000)
    assert projection.notes[0].source_id == note_at(score=score, at=Fraction(0)).id


@pytest.mark.unit
def test_a_note_that_sounds_outside_the_midi_range_is_refused_with_its_name() -> None:
    score: Score = _score()
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, step=40)
    high: Note = note_at(score=score, at=Fraction(0))

    with pytest.raises(ValueError, match=high.id):
        build_projection(document=score.document)


@pytest.mark.unit
def test_a_score_with_no_notes_is_silence_as_long_as_the_score() -> None:
    projection: PlaybackProjection = build_projection(document=_score().document)

    assert projection.notes == ()
    assert projection.extent_ms == pytest.approx(4000)


@pytest.mark.unit
def test_a_repeated_note_is_played_in_each_pass() -> None:
    score: Score = _score()
    quarters(score=score, measure=0, beats=(0,))
    Refrain.create(
        start=anchor_at(score=score, at=Fraction(0)),
        end=anchor_at(score=score, at=Fraction(1)),
        times=2,
    )

    projection: PlaybackProjection = build_projection(document=score.document)

    assert [note.start_ms for note in projection.notes] == [pytest.approx(0), pytest.approx(2000)]
    assert projection.extent_ms == pytest.approx(6000)


@pytest.mark.unit
def test_tied_notes_are_one_note() -> None:
    score: Score = _score()
    quarters(score=score, measure=0, beats=(0, 1))
    Tie.create(
        start_note=note_at(score=score, at=Fraction(0)),
        end_note=note_at(score=score, at=_Q),
    )

    projection: PlaybackProjection = build_projection(document=score.document)

    assert _shapes(projection=projection) == [(64, pytest.approx(0), pytest.approx(1000), 31)]


@pytest.mark.unit
def test_a_start_in_the_score_plays_what_follows_and_strikes_a_sounding_note_again() -> None:
    score: Score = _score()
    quarters(score=score, measure=0, beats=(0, 1))

    projection: PlaybackProjection = build_projection(document=score.document, start=Fraction(1, 8))

    assert _shapes(projection=projection) == [
        (64, pytest.approx(0), pytest.approx(250), 31),
        (64, pytest.approx(250), pytest.approx(750), 31),
    ]
    assert projection.extent_ms == pytest.approx(4000 - 250)


@pytest.mark.unit
def test_a_start_at_the_end_of_the_score_is_nothing_to_play() -> None:
    score: Score = _score()
    quarters(score=score, measure=0, beats=(0,))

    projection: PlaybackProjection = build_projection(document=score.document, start=Fraction(2))

    assert projection == PlaybackProjection(notes=(), extent_ms=0.0)


@pytest.mark.unit
@pytest.mark.parametrize("start", [Fraction(-1, 4), Fraction(9, 4)])
def test_a_start_outside_the_score_is_refused(start: Fraction) -> None:
    with pytest.raises(ValueError, match="outside"):
        build_projection(document=_score().document, start=start)


def _chord() -> tuple[Score, NoteCarrier]:
    score: Score = _score()
    quarters(score=score, measure=0, beats=(0,))
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)

    return score, note_at(score=score, at=Fraction(0)).note_carrier


@pytest.mark.unit
def test_the_preview_of_a_chord_strikes_all_its_notes_together() -> None:
    score, carrier = _chord()

    projection: PlaybackProjection = preview_chord(document=score.document, carrier=carrier)

    assert [(note.source_id, note.start_ms, note.end_ms) for note in projection.notes] == [
        (note.id, 0.0, 650.0) for note in carrier.notes
    ]
    assert {note.velocity for note in projection.notes} == {31}
    assert projection.extent_ms == 650.0


@pytest.mark.unit
def test_the_preview_can_name_the_notes_and_the_time() -> None:
    score, carrier = _chord()
    upper: Note = carrier.notes[1]

    projection: PlaybackProjection = preview_chord(
        document=score.document,
        carrier=carrier,
        note_ids=[upper.id, upper.id],
        duration_ms=300.0,
    )

    assert [(note.source_id, note.end_ms) for note in projection.notes] == [(upper.id, 300.0)]


@pytest.mark.unit
def test_the_preview_has_the_velocity_of_a_mark_of_loudness() -> None:
    score, carrier = _chord()
    carrier.set_articulations(articulations=frozenset({Articulation.ACCENT}))

    projection: PlaybackProjection = preview_chord(document=score.document, carrier=carrier)

    assert {note.velocity for note in projection.notes} == {56}


@pytest.mark.unit
def test_the_preview_refuses_an_empty_or_a_foreign_choice_of_notes() -> None:
    score, carrier = _chord()
    with pytest.raises(ValueError, match="at least one"):
        preview_chord(document=score.document, carrier=carrier, note_ids=[])

    with pytest.raises(ValueError, match="do not belong"):
        preview_chord(document=score.document, carrier=carrier, note_ids=["no-such-note"])
