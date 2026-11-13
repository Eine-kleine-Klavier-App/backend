from collections.abc import Callable
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import RhythmicValue
from piano_app.domain.score.document.models.relations import Relation
from piano_app.domain.score.document.services.mutation.compiler import TieNotesIntent
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)

from ...scene import (
    Score,
    Snapshot,
    TieSlot,
    apply_intent,
    build_score,
    build_two_voices,
    crossing_half,
    insert_note,
    note_at,
    quarters,
    snapshot,
    triplet_scene,
)

# A tie between two existing notes, end to end: compiled from its intent and decided by the
# tie's analyzer against the live document. Ties change no rhythm, so every other part of the
# score must come out as it went in.

_Q: Fraction = Fraction(1, 4)
_THIRD: Fraction = Fraction(1, 12)  # one triplet eighth on the timeline

type TieScene = Callable[[], tuple[Score, Note, Note]]


def _tie(*, score: Score, start: Note, end: Note) -> MutationLog:
    return apply_intent(
        score=score,
        intent=TieNotesIntent(start_note_id=start.id, end_note_id=end.id),
    )


def _chord_before_a_quarter() -> Score:
    """A chord of staff steps 0 and NEW_STEP on beat one, then quarters on staff step 0."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)

    return score


# --- refusals -----------------------------------------------------------------------------


def _the_first_piece_of_a_crossing_half() -> tuple[Score, Note, Note]:
    """The two pieces of a half across the barline are tied already."""
    score: Score = crossing_half()

    return score, note_at(score=score, at=Fraction(3, 4)), note_at(score=score, at=Fraction(1))


def _a_second_chord_note_into_a_tied_note() -> tuple[Score, Note, Note]:
    """The chord's lower note is tied to the quarter after it; its upper note asks for the
    same end."""
    score: Score = _chord_before_a_quarter()
    lower, upper = note_at(score=score, at=Fraction(0)).note_carrier.notes
    end: Note = note_at(score=score, at=_Q)
    _tie(score=score, start=lower, end=end)

    return score, upper, end


def _notes_of_two_voices() -> tuple[Score, Note, Note]:
    """Beat one of voice one and beat two of voice two, which touch on the timeline."""
    first, second = build_two_voices(measure_count=1)
    quarters(score=first, measure=0)
    quarters(score=second, measure=0)

    return first, note_at(score=first, at=Fraction(0)), note_at(score=second, at=_Q)


def _notes_around_a_sleeping_measure() -> tuple[Score, Note, Note]:
    """Measure two is asleep: the last note of measure one and the first of measure three
    are neighbouring leaves of the voice, yet they do not touch."""
    score: Score = build_score(measure_count=3)
    quarters(score=score, measure=0)
    quarters(score=score, measure=2)

    return score, note_at(score=score, at=Fraction(3, 4)), note_at(score=score, at=Fraction(2))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("scene", "match"),
    [
        pytest.param(
            _the_first_piece_of_a_crossing_half,
            "already starts another tie",
            id="a note already starting a tie",
        ),
        pytest.param(
            _a_second_chord_note_into_a_tied_note,
            "already ends another tie",
            id="a note already ending a tie",
        ),
        pytest.param(_notes_of_two_voices, "must touch in one voice", id="two voices"),
        pytest.param(
            _notes_around_a_sleeping_measure,
            "must touch in one voice",
            id="neighbours that do not touch",
        ),
    ],
)
def test_a_refused_tie_leaves_the_score_exactly_as_it_was(scene: TieScene, match: str) -> None:
    score, start, end = scene()
    before: Snapshot = snapshot(score=score)
    start_relations: list[Relation] = list(start.relations)
    end_relations: list[Relation] = list(end.relations)

    with pytest.raises(MutationRejectedError, match=match):
        _tie(score=score, start=start, end=end)

    assert snapshot(score=score) == before
    assert list(start.relations) == start_relations
    assert list(end.relations) == end_relations


# --- ties that hold -----------------------------------------------------------------------


@pytest.mark.unit
def test_two_quarters_on_both_sides_of_a_barline_are_tied() -> None:
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1)
    before: Snapshot = snapshot(score=score)

    _tie(
        score=score,
        start=note_at(score=score, at=Fraction(3, 4)),
        end=note_at(score=score, at=Fraction(1)),
    )

    leaves, groups, _, anchors = before
    assert snapshot(score=score) == (
        leaves,
        groups,
        [TieSlot(start=(0, Fraction(3, 4), 0), end=(1, Fraction(0), 0))],
        anchors,
    )


@pytest.mark.unit
def test_the_last_note_of_a_tuplet_is_tied_to_the_note_after_the_tuplet() -> None:
    """The triplet's last eighth and the next quarter are neighbouring leaves of the voice
    that touch, though they lie in different scopes."""
    score: Score = triplet_scene()
    # a tie joins notes of one pitch
    note_at(score=score, at=Fraction(1, 2)).set_staff_step(staff_step=3)
    before: Snapshot = snapshot(score=score)

    _tie(
        score=score,
        start=note_at(score=score, at=_Q + 2 * _THIRD),
        end=note_at(score=score, at=Fraction(1, 2)),
    )

    leaves, groups, _, anchors = before
    assert snapshot(score=score) == (
        leaves,
        groups,
        [TieSlot(start=(0, _Q + 2 * _THIRD, 3), end=(0, Fraction(1, 2), 3))],
        anchors,
    )


@pytest.mark.unit
def test_one_note_of_a_chord_is_tied_and_the_others_stay_untied() -> None:
    score: Score = _chord_before_a_quarter()
    carrier: NoteCarrier = note_at(score=score, at=Fraction(0)).note_carrier
    lower, upper = carrier.notes
    leaves, groups, _, anchors = snapshot(score=score)

    _tie(score=score, start=lower, end=note_at(score=score, at=_Q))

    assert snapshot(score=score) == (
        leaves,
        groups,
        [TieSlot(start=(0, Fraction(0), 0), end=(0, _Q, 0))],
        anchors,
    )
    assert list(upper.relations) == []


@pytest.mark.unit
def test_rolling_back_a_tie_unties_both_notes() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    before: Snapshot = snapshot(score=score)
    start: Note = note_at(score=score, at=Fraction(0))
    end: Note = note_at(score=score, at=_Q)

    log: MutationLog = _tie(score=score, start=start, end=end)
    log.rollback()

    assert snapshot(score=score) == before
    assert list(start.relations) == []
    assert list(end.relations) == []
