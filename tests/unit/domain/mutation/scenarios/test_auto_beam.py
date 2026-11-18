from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import Carrier, NoteCarrier
from piano_app.domain.score.document.models.notation import RhythmicValue
from piano_app.domain.score.document.models.relations import Beam
from piano_app.domain.score.document.services.helpers import iter_leaves

from ...scene import Score, build_score, build_score_with, insert_note, size

# A note entered by the editor is beamed with the note before it (owner, 2026-11-17): the new note
# is an eighth or shorter and is not added to a chord; the one before it is a note of an eighth or
# shorter, in the same scope and measure, ending where the new one starts, and the beam it would
# join, up to the new note, holds less than its share of the measure (owner, 2026-11-17: half by
# default, a setting of the editor; 0 beams nothing). It takes the place after that note in its
# beam, or the two make a beam.

_E: Fraction = Fraction(1, 8)


def _beams(*, score: Score) -> list[Beam]:
    beams: list[Beam] = []
    for leaf in iter_leaves(score.voice):
        carrier: Carrier | None = leaf.carrier
        if carrier is None:
            continue

        for relation in carrier.carrier_group_relations:
            if isinstance(relation, Beam) and not any(relation is beam for beam in beams):
                beams.append(relation)

    return beams


def _steps(*, score: Score) -> list[list[int]]:
    steps: list[list[int]] = []
    for beam in _beams(score=score):
        members: list[int] = []
        for member in beam.members:
            assert isinstance(member, NoteCarrier)
            members.append(member.notes[0].staff_step)

        steps.append(members)

    return steps


@pytest.mark.unit
def test_an_eighth_after_an_eighth_makes_a_beam_and_a_sixteenth_joins_it() -> None:
    score: Score = build_score(measure_count=1)

    insert_note(score=score, at=0 * _E, rhythmic_value=RhythmicValue.EIGHTH, step=1)
    assert _beams(score=score) == []

    insert_note(score=score, at=1 * _E, rhythmic_value=RhythmicValue.SIXTEENTH, step=2)
    (beam,) = _beams(score=score)
    assert _steps(score=score) == [[1, 2]]

    insert_note(score=score, at=Fraction(3, 16), rhythmic_value=RhythmicValue.SIXTEENTH, step=3)
    assert _steps(score=score) == [[1, 2, 3]]
    assert _beams(score=score)[0] is beam


@pytest.mark.unit
@pytest.mark.parametrize(
    ("beam_share", "expected"),
    [
        (Fraction(0), []),
        (Fraction(1, 4), [[1, 2], [3, 4], [5, 6], [7, 8]]),
        (Fraction(1, 2), [[1, 2, 3, 4], [5, 6, 7, 8]]),
        (Fraction(1), [[1, 2, 3, 4, 5, 6, 7, 8]]),
    ],
)
def test_a_beam_holds_its_share_of_the_measure_then_the_next_note_begins_another(
    beam_share: Fraction, expected: list[list[int]]
) -> None:
    score: Score = build_score(measure_count=1)

    for index in range(8):
        insert_note(
            score=score,
            at=index * _E,
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index + 1,
            beam_share=beam_share,
        )

    assert _steps(score=score) == expected


@pytest.mark.unit
def test_half_of_a_six_eight_measure_is_three_eighths_whatever_the_notes_are() -> None:
    score: Score = build_score_with(time_signatures=[size(RhythmicValue.EIGHTH, count=6)])

    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.EIGHTH, dots=1, step=1)
    insert_note(score=score, at=Fraction(3, 16), rhythmic_value=RhythmicValue.SIXTEENTH, step=2)
    for index, step in enumerate((3, 4, 5, 6)):
        insert_note(
            score=score,
            at=Fraction(1, 4) + index * _E,
            rhythmic_value=RhythmicValue.EIGHTH,
            step=step,
        )

    assert _steps(score=score) == [[1, 2, 3], [4, 5, 6]]


@pytest.mark.unit
def test_a_sixteenth_joins_the_beam_of_the_eighth_before_it() -> None:
    score: Score = build_score(measure_count=1)

    insert_note(score=score, at=0 * _E, rhythmic_value=RhythmicValue.EIGHTH, step=1)
    insert_note(score=score, at=1 * _E, rhythmic_value=RhythmicValue.SIXTEENTH, step=2)

    assert _steps(score=score) == [[1, 2]]


@pytest.mark.unit
def test_what_does_not_touch_or_is_too_long_is_not_beamed() -> None:
    gap: Score = build_score(measure_count=1)
    insert_note(score=gap, at=0 * _E, rhythmic_value=RhythmicValue.EIGHTH, step=1)
    insert_note(score=gap, at=2 * _E, rhythmic_value=RhythmicValue.EIGHTH, step=2)
    assert _beams(score=gap) == []

    after_quarter: Score = build_score(measure_count=1)
    insert_note(score=after_quarter, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, step=1)
    insert_note(score=after_quarter, at=2 * _E, rhythmic_value=RhythmicValue.EIGHTH, step=2)
    assert _beams(score=after_quarter) == []

    before_quarter: Score = build_score(measure_count=1)
    insert_note(score=before_quarter, at=0 * _E, rhythmic_value=RhythmicValue.EIGHTH, step=1)
    insert_note(score=before_quarter, at=1 * _E, rhythmic_value=RhythmicValue.QUARTER, step=2)
    assert _beams(score=before_quarter) == []


@pytest.mark.unit
def test_a_beam_does_not_cross_a_barline() -> None:
    score: Score = build_score(measure_count=2)

    insert_note(score=score, at=Fraction(7, 8), rhythmic_value=RhythmicValue.EIGHTH, step=1)
    insert_note(score=score, at=Fraction(1), rhythmic_value=RhythmicValue.EIGHTH, step=2)

    assert _beams(score=score) == []


@pytest.mark.unit
def test_a_note_added_to_a_chord_changes_no_beam() -> None:
    score: Score = build_score(measure_count=1)
    insert_note(score=score, at=0 * _E, rhythmic_value=RhythmicValue.EIGHTH, step=1)
    insert_note(score=score, at=1 * _E, rhythmic_value=RhythmicValue.EIGHTH, step=2)

    insert_note(score=score, at=1 * _E, rhythmic_value=RhythmicValue.EIGHTH, step=3)

    (beam,) = _beams(score=score)
    assert len(beam.members) == 2


@pytest.mark.unit
def test_one_undo_takes_back_the_note_and_its_beam() -> None:
    score: Score = build_score(measure_count=1)
    insert_note(score=score, at=0 * _E, rhythmic_value=RhythmicValue.EIGHTH, step=1)

    log = insert_note(score=score, at=1 * _E, rhythmic_value=RhythmicValue.EIGHTH, step=2)
    assert _steps(score=score) == [[1, 2]]

    log.rollback()

    assert _beams(score=score) == []
