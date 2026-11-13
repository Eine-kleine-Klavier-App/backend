from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.notation import DottedRhythmicValue, RhythmicValue
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.helpers import iter_leaves
from piano_app.domain.score.document.services.mutation.compiler import CreateTupletWithRestIntent
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)

from ...scene import (
    GroupSlot,
    Score,
    Shape,
    Snapshot,
    apply_intent,
    build_score,
    orphan_anchors,
    quarters,
    rest_at,
    shape,
    size,
    slot,
    snapshot,
    value,
)

# A tuplet created with its first rest, end to end. The fill never touches the first rest,
# so it keeps its value; rests are still compared through ``shape``, which leaves their
# spelling out.

_Q: Fraction = Fraction(1, 4)


def _triplet_on_beat_four(*, score: Score, first: DottedRhythmicValue) -> MutationLog:
    """A quarter triplet from beat four, sounding a half across the barline."""
    return apply_intent(
        score=score,
        intent=CreateTupletWithRestIntent(
            voice_id=score.voice.id,
            staff_id=score.staff.id,
            measure_id=score.measures[0].id,
            position=MeasurePosition.of_fraction(fraction=Fraction(3, 4)),
            written_size=size(RhythmicValue.QUARTER, count=3),
            occupied_size=size(RhythmicValue.HALF),
            written_value=first,
        ),
    )


def _two_measures_of_quarters() -> Score:
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1)

    return score


@pytest.mark.unit
def test_a_first_rest_longer_than_its_tuplet_is_refused_and_changes_nothing() -> None:
    """A written whole does not fit the triplet's three written quarters: the tuplet the
    gesture already created goes with it."""
    score: Score = _two_measures_of_quarters()
    before: Snapshot = snapshot(score=score)
    leaves: list[LeafRhythmicContainer] = iter_leaves(score.voice)

    with pytest.raises(MutationRejectedError, match="does not fit in its scope"):
        _triplet_on_beat_four(score=score, first=value(RhythmicValue.WHOLE))

    assert snapshot(score=score) == before
    assert all(kept is leaf for kept, leaf in zip(iter_leaves(score.voice), leaves, strict=True))


@pytest.mark.unit
def test_a_first_rest_crossing_the_barline_is_cut_there_without_a_tie() -> None:
    """A written half from the triplet's start runs past the barline: it is cut there like
    a note, but its pieces are not tied. The triplet's whole interior is rests, one of them
    starting on the barline, and nothing else of the score moves. The anchors are left out
    on purpose: the ones after the barline depend on the open first-rest question."""
    score: Score = _two_measures_of_quarters()

    _triplet_on_beat_four(score=score, first=value(RhythmicValue.HALF))

    assert shape(score=score) == Shape(
        groups=[
            GroupSlot(
                measure_index=0,
                position=Fraction(3, 4),
                written=size(RhythmicValue.QUARTER, count=3),
                occupied=size(RhythmicValue.HALF),
                depth=0,
            )
        ],
        notes=[
            *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
            *[slot(1, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
        ],
        ties=[],
        rests=[(Fraction(3, 4), Fraction(5, 4), 1)],
    )
    assert rest_at(score=score, at=Fraction(3, 4)).staff is score.staff
    assert rest_at(score=score, at=Fraction(1)).staff is score.staff
    assert orphan_anchors(score=score) == []
