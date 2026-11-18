from collections.abc import Callable
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import Carrier, NoteCarrier
from piano_app.domain.score.document.models.notation import RhythmicValue
from piano_app.domain.score.document.models.relations import Beam
from piano_app.domain.score.document.services.helpers import iter_leaves
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog

from ...scene import (
    Score,
    apply_intent,
    build_score,
    create_tuplet_with_note,
    eighth_triplet,
    find_carriers,
    insert_note,
    note,
    note_at,
    orphan_anchors,
    planned_intent,
    quarters,
    size,
    value,
)

# Beams when elements are overwritten (editing-intents-2026-10, owner 2026-10-19), one rule
# for every overwrite — insert, resize, tuplet creation, cleared frames: the met elements go
# and the beam stays on the runs of consecutive elements that remain (a b c d e f with c d
# overwritten → a-b and e-f); a run of one element has no beam. The beam itself keeps the
# first run of two or more, a later run gets a beam of its own. An element resized to a
# quarter or longer leaves its beam the same way (relation-guard).

_Q: Fraction = Fraction(1, 4)
_E: Fraction = Fraction(1, 8)


def _six_beamed_eighths() -> tuple[Score, Beam]:
    """Build six beamed eighths (staff steps 1-6) and a quarter on beat four."""
    score: Score = build_score(measure_count=1)
    for index in range(6):
        note(
            score=score,
            parent=score.voice,
            at=index * _E,
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index + 1,
        )
    quarters(score=score, measure=0, beats=(3,))
    carriers: list[Carrier] = [
        note_at(score=score, at=index * _E).note_carrier for index in range(6)
    ]

    return score, Beam.create(carriers=carriers)


def _beamed_steps(*, score: Score) -> list[list[int]]:
    """Every beam of the voice as the staff steps of its elements, in timeline order."""
    beams: list[Beam] = []
    for leaf in iter_leaves(score.voice):
        carrier: Carrier | None = leaf.carrier
        if carrier is None:
            continue
        for relation in carrier.carrier_group_relations:
            if isinstance(relation, Beam) and not any(relation is beam for beam in beams):
                beams.append(relation)

    steps: list[list[int]] = []
    for beam in beams:
        members: list[int] = []
        for member in beam.members:
            assert isinstance(member, NoteCarrier)
            members.append(member.notes[0].staff_step)
        steps.append(members)

    return steps


def _quarter_triplet_at(*, score: Score, at: Fraction) -> None:
    """Create three eighths in the time of a quarter at ``at``, starting with an eighth."""
    create_tuplet_with_note(
        score=score,
        at=at,
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
        first=value(RhythmicValue.EIGHTH),
    )


# --- insert (placed spans) ------------------------------------------------------------------


@pytest.mark.unit
def test_a_note_over_the_end_of_a_beam_leaves_the_beam_on_the_rest() -> None:
    score, beam = _six_beamed_eighths()
    members: list[Carrier] = list(beam.members)

    insert_note(score=score, at=Fraction(1, 2), rhythmic_value=RhythmicValue.QUARTER)

    assert _beamed_steps(score=score) == [[1, 2, 3, 4]]
    assert list(beam.members) == members[:4]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_note_in_the_middle_of_a_beam_cuts_it_into_the_runs_that_remain() -> None:
    """The quarter over c d leaves a-b on the beam itself and e-f on a new one."""
    score, beam = _six_beamed_eighths()

    insert_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER)

    assert _beamed_steps(score=score) == [[1, 2], [5, 6]]
    assert list(beam.members) == [
        note_at(score=score, at=index * _E).note_carrier for index in (0, 1)
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_run_of_one_element_left_by_an_insert_has_no_beam() -> None:
    """The quarter over b c leaves a alone, unbeamed; the beam keeps d-f."""
    score, beam = _six_beamed_eighths()

    insert_note(score=score, at=_E, rhythmic_value=RhythmicValue.QUARTER)

    assert _beamed_steps(score=score) == [[4, 5, 6]]
    assert list(note_at(score=score, at=Fraction(0)).note_carrier.carrier_group_relations) == []
    assert beam.members[0] is note_at(score=score, at=3 * _E).note_carrier
    assert orphan_anchors(score=score) == []


def _insert_quarter_over_c_d(score: Score) -> MutationLog:
    return insert_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER)


def _tuplet_over_c_d(score: Score) -> MutationLog:
    return create_tuplet_with_note(
        score=score,
        at=_Q,
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
        first=value(RhythmicValue.EIGHTH),
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "overwrite",
    [_insert_quarter_over_c_d, _tuplet_over_c_d],
    ids=["insert", "tuplet"],
)
def test_undo_and_redo_of_a_cut_beam_restore_the_original_beam(
    overwrite: Callable[[Score], MutationLog],
) -> None:
    score, beam = _six_beamed_eighths()
    members: list[Carrier] = list(beam.members)

    log: MutationLog = overwrite(score)
    after: list[list[int]] = _beamed_steps(score=score)
    assert after == [[1, 2], [5, 6]]

    log.rollback()
    assert list(beam.members) == members
    assert all(list(carrier.carrier_group_relations) == [beam] for carrier in members)
    assert _beamed_steps(score=score) == [[1, 2, 3, 4, 5, 6]]

    log.reapply()
    assert _beamed_steps(score=score) == after
    assert list(beam.members) == members[:2]


# --- resize ---------------------------------------------------------------------------------


@pytest.mark.unit
def test_lengthening_onto_the_end_of_a_beam_leaves_the_beam_on_the_rest() -> None:
    """The fourth eighth becomes a quarter over the fifth: the beam stays on a-c, the resized
    quarter leaves it and the sixth is left alone and unbeamed."""
    score, beam = _six_beamed_eighths()
    members: list[Carrier] = list(beam.members)

    apply_intent(
        score=score,
        intent=planned_intent(
            "ChangeDurationIntent",
            carrier_id=note_at(score=score, at=3 * _E).note_carrier.id,
            written_value=value(RhythmicValue.QUARTER),
        ),
    )

    assert _beamed_steps(score=score) == [[1, 2, 3]]
    assert list(beam.members) == members[:3]
    assert list(members[3].carrier_group_relations) == []
    assert list(note_at(score=score, at=5 * _E).note_carrier.carrier_group_relations) == []
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ("resized", "beamed"),
    [
        pytest.param(0, [[3, 4, 5, 6]], id="left"),
        pytest.param(2, [[1, 2], [5, 6]], id="middle"),
        pytest.param(4, [[1, 2, 3, 4]], id="right"),
    ],
)
def test_an_eighth_resized_to_a_quarter_leaves_its_beam(
    resized: int,
    beamed: list[list[int]],
) -> None:
    """The quarter takes the eighth after it and leaves the beam; what remains on either side
    stays beamed as a run of two or more."""
    score, _ = _six_beamed_eighths()
    carrier: Carrier = note_at(score=score, at=resized * _E).note_carrier

    apply_intent(
        score=score,
        intent=planned_intent(
            "ChangeDurationIntent",
            carrier_id=carrier.id,
            written_value=value(RhythmicValue.QUARTER),
        ),
    )

    assert _beamed_steps(score=score) == beamed
    assert list(carrier.carrier_group_relations) == []
    assert orphan_anchors(score=score) == []


# --- tuplet creation (displacement) ---------------------------------------------------------


@pytest.mark.unit
def test_a_tuplet_over_the_end_of_a_beam_leaves_the_beam_on_the_rest() -> None:
    score, _ = _six_beamed_eighths()

    _quarter_triplet_at(score=score, at=Fraction(1, 2))

    assert _beamed_steps(score=score) == [[1, 2, 3, 4]]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_tuplet_in_the_middle_of_a_beam_cuts_it_into_the_runs_that_remain() -> None:
    score, _ = _six_beamed_eighths()

    _tuplet_over_c_d(score)

    assert _beamed_steps(score=score) == [[1, 2], [5, 6]]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_run_of_one_element_left_by_a_tuplet_has_no_beam() -> None:
    score, _ = _six_beamed_eighths()

    _quarter_triplet_at(score=score, at=_E)

    assert _beamed_steps(score=score) == [[4, 5, 6]]
    assert list(note_at(score=score, at=Fraction(0)).note_carrier.carrier_group_relations) == []
    assert orphan_anchors(score=score) == []


# --- cleared frames -------------------------------------------------------------------------


def _beam_over_a_triplet() -> tuple[Score, Beam]:
    """Build eighths (steps 7, 8), an eighth triplet (steps 1-3), eighths (steps 10, 11) and a
    quarter on beat four, every element but the quarter on one beam across the triplet's
    edges."""
    score: Score = build_score(measure_count=1)
    for at, step in ((Fraction(0), 7), (_E, 8)):
        note(score=score, parent=score.voice, at=at, rhythmic_value=RhythmicValue.EIGHTH, step=step)
    triplet = eighth_triplet(score=score, parent=score.voice, at=_Q)
    for at, step in ((Fraction(1, 2), 10), (Fraction(5, 8), 11)):
        note(score=score, parent=score.voice, at=at, rhythmic_value=RhythmicValue.EIGHTH, step=step)
    quarters(score=score, measure=0, beats=(3,))
    carriers: list[Carrier] = [
        note_at(score=score, at=index * _E).note_carrier for index in range(2)
    ]
    carriers.extend(find_carriers(containers=[triplet]))
    carriers.extend(
        note_at(score=score, at=at).note_carrier for at in (Fraction(1, 2), Fraction(5, 8))
    )

    return score, Beam.create(carriers=carriers)


def _lengthen_the_second_eighth(*, score: Score, rhythmic_value: RhythmicValue, dots: int) -> None:
    """Change the eighth on step 8 so its new span clears the triplet after it."""
    apply_intent(
        score=score,
        intent=planned_intent(
            "ChangeDurationIntent",
            carrier_id=note_at(score=score, at=_E).note_carrier.id,
            written_value=value(rhythmic_value, dots),
        ),
    )


@pytest.mark.unit
def test_a_cleared_tuplet_at_the_end_of_what_stays_beamed_leaves_the_beam_on_the_rest() -> None:
    """The eighth on step 8 becomes a half: the triplet is cleared and the eighth on step 10
    is taken. The resized half leaves the beam, so 7 and 11 are left alone and the beam is
    removed."""
    score, beam = _beam_over_a_triplet()
    members: list[Carrier] = list(beam.members)

    _lengthen_the_second_eighth(score=score, rhythmic_value=RhythmicValue.HALF, dots=0)

    assert _beamed_steps(score=score) == []
    assert all(list(member.carrier_group_relations) == [] for member in members[:2])
    assert list(note_at(score=score, at=Fraction(5, 8)).note_carrier.carrier_group_relations) == []
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_lengthening_the_second_element_of_a_beam_leaves_it_on_the_run_after() -> None:
    """The second eighth becomes a quarter over the third: the resized quarter leaves the
    beam, a is left alone and the beam keeps d-f."""
    score, beam = _six_beamed_eighths()
    members: list[Carrier] = list(beam.members)

    apply_intent(
        score=score,
        intent=planned_intent(
            "ChangeDurationIntent",
            carrier_id=members[1].id,
            written_value=value(RhythmicValue.QUARTER),
        ),
    )

    assert _beamed_steps(score=score) == [[4, 5, 6]]
    assert list(beam.members) == members[3:]
    assert list(members[0].carrier_group_relations) == []
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_cleared_tuplet_in_the_middle_of_a_beam_cuts_it_into_the_runs_that_remain() -> None:
    """The eighth on step 8 becomes a dotted quarter over the triplet. The beam is judged once,
    when the gesture ends: 7 is left alone, and the beam itself stays on 10-11."""
    score, beam = _beam_over_a_triplet()
    members: list[Carrier] = list(beam.members)

    _lengthen_the_second_eighth(score=score, rhythmic_value=RhythmicValue.QUARTER, dots=1)

    assert _beamed_steps(score=score) == [[10, 11]]
    assert all(list(member.carrier_group_relations) == [] for member in members[:2])
    assert list(beam.members) == members[-2:]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_beam_is_cut_only_where_an_element_leaves_it_never_at_a_tuplet_edge() -> None:
    """A sixteenth over the last eighth takes only it; the junctions at the triplet's edges,
    which the beam already crossed, stay. The sixteenth itself, a short note touching the beam's
    last, joins the beam: the beam holds less than half the measure."""
    score, beam = _beam_over_a_triplet()
    members: list[Carrier] = list(beam.members)

    insert_note(score=score, at=Fraction(5, 8), rhythmic_value=RhythmicValue.SIXTEENTH)

    assert _beamed_steps(score=score) == [[7, 8, 1, 2, 3, 10, 9]]
    assert list(beam.members)[:-1] == members[:-1]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_one_overwrite_cuts_each_beam_it_meets() -> None:
    """A quarter over the third and fourth eighths, beamed a-c and d-f, cuts both beams."""
    score: Score = build_score(measure_count=1)
    for index in range(6):
        note(
            score=score,
            parent=score.voice,
            at=index * _E,
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index + 1,
        )
    quarters(score=score, measure=0, beats=(3,))
    carriers: list[Carrier] = [
        note_at(score=score, at=index * _E).note_carrier for index in range(6)
    ]
    first: Beam = Beam.create(carriers=carriers[:3])
    second: Beam = Beam.create(carriers=carriers[3:])

    insert_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER)

    assert _beamed_steps(score=score) == [[1, 2], [5, 6]]
    assert (list(first.members), list(second.members)) == (carriers[:2], carriers[4:])
    assert orphan_anchors(score=score) == []
