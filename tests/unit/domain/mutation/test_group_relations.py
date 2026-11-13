from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import NoteCarrier, RestCarrier
from piano_app.domain.score.document.models.notation import RhythmicValue
from piano_app.domain.score.document.models.relations import Beam
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)

from ..scene import (
    Score,
    Snapshot,
    build_engine,
    build_score,
    layout,
    note,
    note_at,
    rest,
    rest_at,
    snapshot,
)

# A group relation the deleted carrier belongs to is deleted with it only when it cannot stay
# valid without that carrier; one that can keeps its other members and loses this one when the
# carrier detaches. A beam lets a member leave from any position while two remain; the gap a
# middle member leaves is the relation guard's to judge (relation-guard). The relation's own
# member list is kept for replay, so whether a relation survives is read from the carriers'
# reverse indexes.

_Q: Fraction = Fraction(1, 4)
_E: Fraction = Fraction(1, 8)


def _carriers(*, score: Score) -> list[NoteCarrier]:
    """The note carriers of a measure of quarters, beat by beat."""
    return [note_at(score=score, at=Fraction(beat, 4)).note_carrier for beat in range(4)]


def _eighths(*, score: Score) -> list[NoteCarrier]:
    """Four eighths from beat one, then a half rest; their note carriers in order."""
    for index in range(4):
        note(
            score=score,
            parent=score.voice,
            at=index * _E,
            rhythmic_value=RhythmicValue.EIGHTH,
            step=0,
        )
    rest(score=score, parent=score.voice, at=Fraction(1, 2), rhythmic_value=RhythmicValue.HALF)

    return [note_at(score=score, at=index * _E).note_carrier for index in range(4)]


def _delete_note_carrier(*, score: Score, carrier: NoteCarrier) -> MutationLog:
    return build_engine().process(
        document=score.document,
        requests=[DeleteRequest(target=carrier)],
    )


@pytest.mark.unit
def test_a_beam_losing_its_edge_carrier_keeps_the_others() -> None:
    score: Score = build_score(measure_count=1)
    carriers: list[NoteCarrier] = _eighths(score=score)
    beam: Beam = Beam.create(carriers=[*carriers[:3]])
    before: Snapshot = snapshot(score=score)

    log: MutationLog = _delete_note_carrier(score=score, carrier=carriers[0])

    assert list(beam.members) == carriers[1:3]
    assert list(carriers[1].carrier_group_relations) == [beam]
    assert list(carriers[2].carrier_group_relations) == [beam]
    assert [entry.content for entry in layout(score=score)] == ["rest", "0", "0", "0", "rest"]

    log.rollback()

    assert list(beam.members) == carriers[:3]
    assert all(list(carrier.carrier_group_relations) == [beam] for carrier in carriers[:3])
    assert snapshot(score=score) == before


@pytest.mark.unit
def test_a_beam_of_two_is_deleted_with_one_of_its_carriers() -> None:
    score: Score = build_score(measure_count=1)
    carriers: list[NoteCarrier] = _eighths(score=score)
    beam: Beam = Beam.create(carriers=[*carriers[:2]])
    before: Snapshot = snapshot(score=score)

    log: MutationLog = _delete_note_carrier(score=score, carrier=carriers[0])

    assert all(list(carrier.carrier_group_relations) == [] for carrier in carriers)

    log.rollback()

    assert all(list(carrier.carrier_group_relations) == [beam] for carrier in carriers[:2])
    assert snapshot(score=score) == before


@pytest.mark.unit
def test_the_guard_removes_a_beam_at_the_gap_its_middle_carrier_leaves() -> None:
    """The middle carrier of three leaves the beam; the two left do not touch, so the relation
    guard removes the beam."""
    score: Score = build_score(measure_count=1)
    carriers: list[NoteCarrier] = _eighths(score=score)
    beam: Beam = Beam.create(carriers=[*carriers[:3]])
    before: Snapshot = snapshot(score=score)

    log: MutationLog = _delete_note_carrier(score=score, carrier=carriers[1])

    assert all(list(carrier.carrier_group_relations) == [] for carrier in carriers)

    log.rollback()

    assert all(list(carrier.carrier_group_relations) == [beam] for carrier in carriers[:3])
    assert snapshot(score=score) == before


def _rest_between_beamed_notes() -> tuple[Score, list[NoteCarrier], RestCarrier]:
    """An eighth note, an eighth rest, two eighth notes, then a half rest."""
    score: Score = build_score(measure_count=1)
    for index in (0, 2, 3):
        note(
            score=score,
            parent=score.voice,
            at=index * _E,
            rhythmic_value=RhythmicValue.EIGHTH,
            step=0,
        )
    rest(score=score, parent=score.voice, at=_E, rhythmic_value=RhythmicValue.EIGHTH)
    rest(score=score, parent=score.voice, at=Fraction(1, 2), rhythmic_value=RhythmicValue.HALF)
    carriers: list[NoteCarrier] = [
        note_at(score=score, at=index * _E).note_carrier for index in (0, 2, 3)
    ]

    return score, carriers, rest_at(score=score, at=_E).rest_carrier


@pytest.mark.unit
def test_the_guard_removes_a_beam_at_the_gap_its_middle_rest_carrier_leaves() -> None:
    """The rest carrier leaves the beam; the two notes left do not touch, so the relation
    guard removes the beam before the fill refills the rest's room."""
    score, carriers, rest_carrier = _rest_between_beamed_notes()
    beam: Beam = Beam.create(carriers=[carriers[0], rest_carrier, carriers[1]])
    before: Snapshot = snapshot(score=score)

    log: MutationLog = build_engine().process(
        document=score.document,
        requests=[DeleteRequest(target=rest_carrier)],
    )

    assert list(carriers[0].carrier_group_relations) == []
    assert list(carriers[1].carrier_group_relations) == []
    # the rest's room is refilled by a new rest
    assert layout(score=score) == before[0]
    assert rest_at(score=score, at=_E).rest_carrier is not rest_carrier

    log.rollback()

    assert list(rest_carrier.carrier_group_relations) == [beam]
    assert rest_at(score=score, at=_E).rest_carrier is rest_carrier
    assert snapshot(score=score) == before


@pytest.mark.unit
def test_a_beam_losing_a_rest_carrier_at_its_edge_keeps_the_others() -> None:
    score, carriers, rest_carrier = _rest_between_beamed_notes()
    beam: Beam = Beam.create(carriers=[rest_carrier, carriers[1], carriers[2]])

    build_engine().process(
        document=score.document,
        requests=[DeleteRequest(target=rest_carrier)],
    )

    assert list(beam.members) == carriers[1:]
    assert list(carriers[1].carrier_group_relations) == [beam]
    assert list(carriers[2].carrier_group_relations) == [beam]
