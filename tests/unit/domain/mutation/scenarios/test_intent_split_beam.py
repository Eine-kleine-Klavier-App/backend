from collections.abc import Sequence
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import Carrier
from piano_app.domain.score.document.models.notation import RhythmicValue
from piano_app.domain.score.document.models.relations import Beam
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.helpers import find_beams
from piano_app.domain.score.document.services.mutation.compiler import (
    SplitBeamIntent,
    build_compiler,
)
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    SplitBeamRequest,
)

from ...scene import (
    Score,
    apply_intent,
    build_score,
    group,
    note,
    quarters,
    rest,
    size,
    snapshot,
)


def _carrier(leaf: LeafRhythmicContainer) -> Carrier:
    assert leaf.carrier is not None
    return leaf.carrier


def _line(count: int, rest_indices: Sequence[int] = ()) -> tuple[Score, list[Carrier], Beam]:
    score = build_score(measure_count=1)
    members = []
    for index in range(8):
        leaf = (
            note(
                score=score,
                parent=score.voice,
                at=Fraction(index, 8),
                rhythmic_value=RhythmicValue.EIGHTH,
                step=index,
            )
            if index < count and index not in rest_indices
            else rest(
                score=score,
                parent=score.voice,
                at=Fraction(index, 8),
                rhythmic_value=RhythmicValue.EIGHTH,
            )
        )
        if index < count:
            members.append(_carrier(leaf))
    return score, members, Beam.create(carriers=members)


def _member_ids(carriers: Sequence[Carrier]) -> list[list[str]]:
    return [[member.id for member in beam.members] for beam in find_beams(carriers=carriers)]


@pytest.mark.unit
@pytest.mark.parametrize(("count", "boundary"), [(4, 2), (3, 1), (3, 2), (2, 1), (6, 3)])
def test_split_preserves_material_and_is_one_reversible_gesture(count: int, boundary: int) -> None:
    score, members, beam = _line(count)
    before = snapshot(score=score)
    owners = [member.owner for member in members]
    ids = [member.id for member in members]

    requests = build_compiler().compile(
        document=score.document,
        intent=SplitBeamIntent(beam_id=beam.id, before_carrier_id=members[boundary].id),
    )
    assert requests == [SplitBeamRequest(target=beam, before_carrier=members[boundary])]
    log = apply_intent(
        score=score,
        intent=SplitBeamIntent(beam_id=beam.id, before_carrier_id=members[boundary].id),
    )

    expected = [run for run in (ids[:boundary], ids[boundary:]) if len(run) >= 2]
    assert _member_ids(members) == expected
    assert snapshot(score=score) == before
    assert [member.owner for member in members] == owners
    if expected:
        assert find_beams(carriers=members)[0] is beam
    after_ids = [found.id for found in find_beams(carriers=members)]

    log.rollback()
    assert find_beams(carriers=members) == [beam]
    assert list(beam.members) == members
    assert snapshot(score=score) == before
    log.reapply()
    assert _member_ids(members) == expected
    assert [found.id for found in find_beams(carriers=members)] == after_ids
    assert snapshot(score=score) == before


@pytest.mark.unit
@pytest.mark.parametrize("boundary", [1, 2, 3])
def test_a_rest_can_be_the_split_member_without_losing_its_carrier(boundary: int) -> None:
    score, members, beam = _line(4, rest_indices=(boundary,))
    before = snapshot(score=score)
    apply_intent(
        score=score, intent=SplitBeamIntent(beam_id=beam.id, before_carrier_id=members[boundary].id)
    )
    ids = [member.id for member in members]
    assert _member_ids(members) == [
        run for run in (ids[:boundary], ids[boundary:]) if len(run) >= 2
    ]
    assert snapshot(score=score) == before


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad", ["first", "foreign", "missing-beam", "missing-member", "wrong-beam-type", "note-id"]
)
def test_invalid_split_rejects_without_changing_the_beam_or_material(bad: str) -> None:
    score, members, beam = _line(4)
    before = snapshot(score=score)
    beam_id, carrier_id = beam.id, members[2].id
    if bad == "first":
        carrier_id = members[0].id
    elif bad == "foreign":
        foreign = score.voice.children[-1]
        assert isinstance(foreign, LeafRhythmicContainer)
        carrier_id = _carrier(foreign).id
    elif bad == "missing-beam":
        beam_id = "missing"
    elif bad == "missing-member":
        carrier_id = "missing"
    elif bad == "wrong-beam-type":
        beam_id = members[0].id
    else:
        from piano_app.domain.score.document.models.material import NoteCarrier

        carrier = members[2]
        assert isinstance(carrier, NoteCarrier)
        carrier_id = carrier.notes[0].id
    with pytest.raises(MutationRejectedError):
        apply_intent(
            score=score, intent=SplitBeamIntent(beam_id=beam_id, before_carrier_id=carrier_id)
        )
    assert snapshot(score=score) == before
    assert find_beams(carriers=members) == [beam]
    assert list(beam.members) == members


@pytest.mark.unit
def test_split_at_a_barline_keeps_both_contiguous_runs_and_their_positions() -> None:
    score = build_score(measure_count=2)
    members = []
    for index in range(16):
        if 6 <= index < 10:
            leaf = note(
                score=score,
                parent=score.voice,
                at=Fraction(index, 8),
                rhythmic_value=RhythmicValue.EIGHTH,
                step=index,
            )
            members.append(_carrier(leaf))
        else:
            rest(
                score=score,
                parent=score.voice,
                at=Fraction(index, 8),
                rhythmic_value=RhythmicValue.EIGHTH,
            )
    beam = Beam.create(carriers=members)
    before = snapshot(score=score)
    apply_intent(
        score=score, intent=SplitBeamIntent(beam_id=beam.id, before_carrier_id=members[2].id)
    )
    assert _member_ids(members) == [[m.id for m in members[:2]], [m.id for m in members[2:]]]
    assert snapshot(score=score) == before


@pytest.mark.unit
def test_split_within_nested_tuplets_keeps_the_groups_and_all_written_values() -> None:
    score = build_score(measure_count=1)
    outer = group(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    inner = group(
        score=score,
        parent=outer,
        at=Fraction(0),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
    )
    members = [
        _carrier(
            note(
                score=score,
                parent=inner,
                at=Fraction(i, 36),
                rhythmic_value=RhythmicValue.EIGHTH,
                step=i,
            )
        )
        for i in range(3)
    ]
    members.extend(
        _carrier(
            note(score=score, parent=outer, at=at, rhythmic_value=RhythmicValue.EIGHTH, step=4)
        )
        for at in (Fraction(1, 12), Fraction(1, 6))
    )
    quarters(score=score, measure=0, beats=(1, 2, 3))
    beam = Beam.create(carriers=members)
    before = snapshot(score=score)
    apply_intent(
        score=score, intent=SplitBeamIntent(beam_id=beam.id, before_carrier_id=members[2].id)
    )
    assert _member_ids(members) == [[m.id for m in members[:2]], [m.id for m in members[2:]]]
    assert snapshot(score=score) == before
    assert inner.parent is outer
