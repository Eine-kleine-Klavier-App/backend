from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import Carrier, Note, Rest
from piano_app.domain.score.document.models.notation import GlissandoType, RhythmicValue
from piano_app.domain.score.document.models.relations import Beam, Glissando
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)

from ...scene import (
    GroupSlot,
    Piano,
    Score,
    Snapshot,
    anchor_layout,
    apply_intent,
    build_piano,
    build_score,
    crossing_half,
    four_quarters,
    group_layout,
    layout,
    note,
    note_at,
    numbered_quarters,
    orphan_anchors,
    pending,
    planned_intent,
    quarters,
    rest,
    rest_at,
    size,
    slot,
    snapshot,
    tie_layout,
    triplet_scene,
    value,
)

# InsertRest end to end (editing-intents-2026-10): like InsertNote with rest content — the
# groups it meets are cleared, its spans placed with per-element overwrite, cut at barlines
# into untied rest pieces, and it never joins what it lands on.

_Q: Fraction = Fraction(1, 4)
_H: Fraction = Fraction(1, 2)
_E: Fraction = Fraction(1, 8)
_THIRD: Fraction = Fraction(1, 12)  # one triplet eighth on the timeline

_PENDING = pending(stage=2)


def insert_rest(
    *,
    score: Score,
    at: Fraction,
    rhythmic_value: RhythmicValue,
    dots: int = 0,
) -> MutationLog:
    """Run ``InsertRestIntent(voice_id, staff_id, measure_id, position, written_value)``.

    The fields of ``InsertNoteIntent`` without pitch, fingering and accidental;
    ``written_value`` is read in the units of the scope the rest lands in.
    """
    return apply_intent(
        score=score,
        intent=planned_intent(
            "InsertRestIntent",
            voice_id=score.voice.id,
            staff_id=score.staff.id,
            measure_id=score.measures[int(at)].id,
            position=MeasurePosition.of_fraction(fraction=at - int(at)),
            written_value=value(rhythmic_value, dots),
        ),
    )


@pytest.mark.unit
@_PENDING
def test_a_rest_in_a_sleeping_measure_wakes_it_on_the_staff_it_names() -> None:
    """A quarter rest on the lower staff wakes the empty measure two; fill follows its staff.

    One voice over two staffs: measure one holds quarters on the upper staff. The rest is
    the only thing of the voice in measure two, so the rests fill tiles around it go to the
    lower staff too.
    """
    piano: Piano = build_piano(measure_count=2)
    upper: Score = Score(
        document=piano.document,
        voice=piano.voice,
        staff=piano.upper,
        measures=piano.measures,
    )
    lower: Score = Score(
        document=piano.document,
        voice=piano.voice,
        staff=piano.lower,
        measures=piano.measures,
    )
    quarters(score=upper, measure=0)

    insert_rest(score=lower, at=1 + _Q, rhythmic_value=RhythmicValue.QUARTER)

    assert layout(score=lower) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(4)],
        slot(1, Fraction(0), _Q, "rest"),
        slot(1, _Q, _Q, "rest"),
        slot(1, _H, _H, "rest"),
    ]
    assert [rest_at(score=lower, at=at).staff for at in (Fraction(1), 1 + _Q, 1 + _H)] == [
        piano.lower,
        piano.lower,
        piano.lower,
    ]
    assert group_layout(score=lower) == []
    assert tie_layout(score=lower) == []
    assert anchor_layout(score=lower) == [
        *[(0, Fraction(beat, 4)) for beat in range(4)],
        (1, Fraction(0)),
        (1, _Q),
        (1, _H),
    ]
    assert orphan_anchors(score=lower) == []


@pytest.mark.unit
@_PENDING
def test_a_quarter_rest_over_a_half_rest_replaces_it_and_fill_takes_the_rest() -> None:
    """The half rest on beat two is met and removed; fill tiles beat three after the new rest."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    rest(score=score, parent=score.voice, at=_Q, rhythmic_value=RhythmicValue.HALF)
    quarters(score=score, measure=0, beats=(3,))
    old: Rest = rest_at(score=score, at=_Q)

    insert_rest(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "rest"),
        slot(0, _H, _Q, "rest"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert old not in score.staff.musical_items
    assert anchor_layout(score=score) == [(0, Fraction(beat, 4)) for beat in range(4)]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_a_rest_on_a_rest_of_the_same_span_replaces_it() -> None:
    """A rest never joins: the quarter rest on beat two is removed and a new one takes its place."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    rest(score=score, parent=score.voice, at=_Q, rhythmic_value=RhythmicValue.QUARTER)
    quarters(score=score, measure=0, beats=(2, 3))
    old: Rest = rest_at(score=score, at=_Q)

    insert_rest(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "rest"),
        slot(0, _H, _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert rest_at(score=score, at=_Q) is not old
    assert old not in score.staff.musical_items
    assert anchor_layout(score=score) == [(0, Fraction(beat, 4)) for beat in range(4)]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_a_half_rest_over_two_quarters_removes_both() -> None:
    score: Score = four_quarters()

    insert_rest(score=score, at=_Q, rhythmic_value=RhythmicValue.HALF)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _H, "rest"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert group_layout(score=score) == []
    assert tie_layout(score=score) == []
    assert anchor_layout(score=score) == [(0, Fraction(0)), (0, _Q), (0, Fraction(3, 4))]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_a_dotted_half_rest_takes_three_beats() -> None:
    score: Score = four_quarters()

    insert_rest(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.HALF, dots=1)

    assert layout(score=score) == [
        slot(0, Fraction(0), Fraction(3, 4), "rest"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert tie_layout(score=score) == []
    assert anchor_layout(score=score) == [(0, Fraction(0)), (0, Fraction(3, 4))]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_a_half_rest_from_outside_over_a_whole_triplet_clears_the_triplet() -> None:
    """The half rest on beat one covers the quarter and the whole triplet on beat two.

    The triplet is cleared with its eighths, and the rest takes their room.
    """
    score: Score = triplet_scene()

    insert_rest(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.HALF)

    assert layout(score=score) == [
        slot(0, Fraction(0), _H, "rest"),
        slot(0, _H, _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert group_layout(score=score) == []
    assert tie_layout(score=score) == []
    assert anchor_layout(score=score) == [(0, Fraction(0)), (0, _H), (0, Fraction(3, 4))]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_a_rest_on_the_second_piece_of_a_tied_half_removes_that_piece_and_its_tie() -> None:
    """Only the piece met goes, with its tie; the first piece stays, untied.

    The rest of measure two is the scene's own rest, untouched.
    """
    score: Score = crossing_half()

    insert_rest(score=score, at=Fraction(1), rhythmic_value=RhythmicValue.QUARTER)

    assert layout(score=score) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        slot(0, Fraction(3, 4), _Q, "1"),
        slot(1, Fraction(0), _Q, "rest"),
        slot(1, _Q, Fraction(3, 4), "rest"),
    ]
    assert tie_layout(score=score) == []
    assert anchor_layout(score=score) == [
        *[(0, Fraction(beat, 4)) for beat in range(4)],
        (1, Fraction(0)),
        (1, _Q),
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_a_rest_exactly_on_a_note_replaces_it_instead_of_joining() -> None:
    """A rest on the first piece of the tied half removes it with its tie instead of joining.

    InsertNote would join that piece as a chord. The second piece stays, untied.
    """
    score: Score = crossing_half()

    insert_rest(score=score, at=Fraction(3, 4), rhythmic_value=RhythmicValue.QUARTER)

    assert layout(score=score) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        slot(0, Fraction(3, 4), _Q, "rest"),
        slot(1, Fraction(0), _Q, "1"),
        slot(1, _Q, Fraction(3, 4), "rest"),
    ]
    assert tie_layout(score=score) == []
    assert anchor_layout(score=score) == [
        *[(0, Fraction(beat, 4)) for beat in range(4)],
        (1, Fraction(0)),
        (1, _Q),
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_a_half_rest_across_the_barline_is_cut_into_two_untied_rests() -> None:
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1)

    insert_rest(score=score, at=Fraction(3, 4), rhythmic_value=RhythmicValue.HALF)

    assert layout(score=score) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        slot(0, Fraction(3, 4), _Q, "rest"),
        slot(1, Fraction(0), _Q, "rest"),
        *[slot(1, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert tie_layout(score=score) == []
    assert group_layout(score=score) == []
    assert anchor_layout(score=score) == [
        (measure, Fraction(beat, 4)) for measure in range(2) for beat in range(4)
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_an_eighth_rest_in_a_triplet_replaces_its_middle_eighth() -> None:
    """The rest lands inside the triplet, its value read in the triplet's units.

    The triplet and its other eighths stay.
    """
    score: Score = triplet_scene()

    insert_rest(score=score, at=_Q + _THIRD, rhythmic_value=RhythmicValue.EIGHTH)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _E, "1", depth=1),
        slot(0, _Q + _THIRD, _E, "rest", depth=1),
        slot(0, _Q + 2 * _THIRD, _E, "3", depth=1),
        slot(0, _H, _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert group_layout(score=score) == [
        GroupSlot(
            measure_index=0,
            position=_Q,
            written=size(RhythmicValue.EIGHTH, count=3),
            occupied=size(RhythmicValue.QUARTER),
            depth=0,
        )
    ]
    assert tie_layout(score=score) == []
    assert anchor_layout(score=score) == [
        (0, Fraction(0)),
        (0, _Q),
        (0, _Q + _THIRD),
        (0, _Q + 2 * _THIRD),
        (0, _H),
        (0, Fraction(3, 4)),
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_a_rest_past_the_score_end_is_refused_and_changes_nothing() -> None:
    """A half rest on the last beat would run past the last measure: the gesture is refused."""
    score: Score = four_quarters()
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match="does not fit in its scope"):
        insert_rest(score=score, at=Fraction(3, 4), rhythmic_value=RhythmicValue.HALF)

    assert snapshot(score=score) == before


@pytest.mark.unit
@_PENDING
def test_a_rest_over_a_beamed_note_removes_the_beam() -> None:
    """An eighth rest on the second of two beamed eighths takes it; a beam of one cannot stand."""
    score: Score = build_score(measure_count=1)
    for index in range(2):
        note(
            score=score,
            parent=score.voice,
            at=index * _E,
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index + 1,
        )
    quarters(score=score, measure=0, beats=(1, 2, 3))
    first: Carrier = note_at(score=score, at=Fraction(0)).note_carrier
    Beam.create(carriers=[first, note_at(score=score, at=_E).note_carrier])

    insert_rest(score=score, at=_E, rhythmic_value=RhythmicValue.EIGHTH)

    assert layout(score=score) == [
        slot(0, Fraction(0), _E, "1"),
        slot(0, _E, _E, "rest"),
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert list(first.carrier_group_relations) == []
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_a_rest_over_a_glissandos_end_note_removes_the_glissando() -> None:
    score: Score = build_score(measure_count=1)
    numbered_quarters(score=score, measure=0, first_step=1)
    start: Note = note_at(score=score, at=Fraction(0))
    Glissando.create(
        start_note=start,
        end_note=note_at(score=score, at=_Q),
        glissando_type=GlissandoType.STRAIGHT,
    )

    insert_rest(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "1"),
        slot(0, _Q, _Q, "rest"),
        slot(0, _H, _Q, "3"),
        slot(0, Fraction(3, 4), _Q, "4"),
    ]
    assert list(start.relations) == []
    assert orphan_anchors(score=score) == []
