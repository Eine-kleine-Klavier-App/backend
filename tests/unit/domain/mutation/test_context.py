from dataclasses import dataclass

import pytest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import ClefChange, KeySignatureChange
from piano_app.domain.score.document.models.notation import Clef
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition, Staff, Voice
from piano_app.domain.score.document.services.mutation import MutationEngine
from piano_app.domain.score.document.services.mutation.engine.factory import build_engine
from piano_app.domain.score.document.services.mutation.instructions import ResultRef
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateClefChangeRequest,
    CreateKeySignatureChangeRequest,
    DeleteContextRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class _Score:
    document: ScoreDocument
    measure: Measure
    staff_a: Staff
    staff_b: Staff


@pytest.fixture
def score() -> _Score:
    measure: Measure = Measure.create()
    staff_a, staff_b = Staff(), Staff()
    document: ScoreDocument = ScoreDocument.create(
        voices=[Voice()], staffs=[staff_a, staff_b], measures=[measure]
    )

    return _Score(document=document, measure=measure, staff_a=staff_a, staff_b=staff_b)


@pytest.fixture
def engine() -> MutationEngine:
    return build_engine()


@pytest.mark.unit
def test_a_clef_change_creates_its_own_anchor(score: _Score, engine: MutationEngine) -> None:
    log = engine.process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measure,
                position=MeasurePosition.of(numerator=1, denominator=4),
                staff=score.staff_a,
                clef=Clef.BASS,
                out=ResultRef[ClefChange](),
            )
        ],
    )

    assert len(score.measure.anchors) == 1
    anchor = score.measure.anchors[0]
    assert anchor.position == MeasurePosition.of(numerator=1, denominator=4)
    assert len(anchor.starting_contexts) == 1
    clef_change = anchor.starting_contexts[0]
    assert isinstance(clef_change, ClefChange)
    assert clef_change.clef is Clef.BASS and clef_change.staff is score.staff_a

    log.rollback()
    assert score.measure.anchors == []


@pytest.mark.unit
def test_a_second_clef_change_at_the_same_anchor_and_staff_displaces_the_first(
    score: _Score,
    engine: MutationEngine,
) -> None:
    """The invariant: two ClefChange for the same staff at the same anchor cannot
    coexist — the second replaces the first rather than erroring."""
    position = MeasurePosition.of(numerator=0, denominator=1)
    engine.process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measure,
                position=position,
                staff=score.staff_a,
                clef=Clef.TREBLE,
                out=ResultRef[ClefChange](),
            )
        ],
    )
    anchor = score.measure.anchors[0]
    first = anchor.starting_contexts[0]

    engine.process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measure,
                position=position,
                staff=score.staff_a,
                clef=Clef.BASS,
                out=ResultRef[ClefChange](),
            )
        ],
    )

    # no new anchor -- the existing one was reused
    assert len(score.measure.anchors) == 1
    assert len(anchor.starting_contexts) == 1
    survivor = anchor.starting_contexts[0]
    assert isinstance(survivor, ClefChange)
    assert survivor.clef is Clef.BASS
    assert survivor is not first


@pytest.mark.unit
def test_clef_changes_on_different_staves_at_the_same_anchor_coexist(
    score: _Score,
    engine: MutationEngine,
) -> None:
    position = MeasurePosition.of(numerator=0, denominator=1)
    engine.process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measure,
                position=position,
                staff=score.staff_a,
                clef=Clef.TREBLE,
                out=ResultRef[ClefChange](),
            )
        ],
    )
    engine.process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measure,
                position=position,
                staff=score.staff_b,
                clef=Clef.BASS,
                out=ResultRef[ClefChange](),
            )
        ],
    )

    anchor = score.measure.anchors[0]
    assert {ctx.staff for ctx in anchor.starting_contexts if isinstance(ctx, ClefChange)} == {
        score.staff_a,
        score.staff_b,
    }


@pytest.mark.unit
def test_a_clef_change_and_a_key_signature_change_at_the_same_anchor_and_staff_coexist(
    score: _Score,
    engine: MutationEngine,
) -> None:
    """Different types don't conflict -- the invariant is per concrete type, not
    "one context per anchor+staff"."""
    position = MeasurePosition.of(numerator=0, denominator=1)
    engine.process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measure,
                position=position,
                staff=score.staff_a,
                clef=Clef.TREBLE,
                out=ResultRef[ClefChange](),
            )
        ],
    )
    engine.process(
        document=score.document,
        requests=[
            CreateKeySignatureChangeRequest(
                measure=score.measure,
                position=position,
                staff=score.staff_a,
                out=ResultRef[KeySignatureChange](),
            )
        ],
    )

    anchor = score.measure.anchors[0]
    kinds = {type(ctx) for ctx in anchor.starting_contexts}
    assert kinds == {ClefChange, KeySignatureChange}


@pytest.mark.unit
def test_a_second_key_signature_change_displaces_the_first(
    score: _Score,
    engine: MutationEngine,
) -> None:
    position = MeasurePosition.of(numerator=0, denominator=1)
    engine.process(
        document=score.document,
        requests=[
            CreateKeySignatureChangeRequest(
                measure=score.measure,
                position=position,
                staff=score.staff_a,
                out=ResultRef[KeySignatureChange](),
            )
        ],
    )
    engine.process(
        document=score.document,
        requests=[
            CreateKeySignatureChangeRequest(
                measure=score.measure,
                position=position,
                staff=score.staff_a,
                out=ResultRef[KeySignatureChange](),
            )
        ],
    )

    anchor = score.measure.anchors[0]
    key_signature_changes = [
        ctx for ctx in anchor.starting_contexts if isinstance(ctx, KeySignatureChange)
    ]
    assert len(key_signature_changes) == 1


@pytest.mark.unit
def test_deleting_a_context_goes_through_the_generic_path_and_leaves_no_orphan(
    score: _Score,
    engine: MutationEngine,
) -> None:
    """Delete is generic over Context (mirrors DeleteRelationRequest over Relation),
    and the anchor's own orphan cleanup already accounts for context lists."""
    engine.process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measure,
                position=MeasurePosition.of(numerator=0, denominator=1),
                staff=score.staff_a,
                clef=Clef.TREBLE,
                out=ResultRef[ClefChange](),
            )
        ],
    )
    clef_change = score.measure.anchors[0].starting_contexts[0]

    engine.process(document=score.document, requests=[DeleteContextRequest(target=clef_change)])

    # the cleanup postprocessor reaps the now-orphan anchor
    assert score.measure.anchors == []


@pytest.mark.unit
def test_a_second_clef_change_at_a_different_position_gets_its_own_anchor(
    score: _Score,
    engine: MutationEngine,
) -> None:
    engine.process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measure,
                position=MeasurePosition.of(numerator=0, denominator=1),
                staff=score.staff_a,
                clef=Clef.TREBLE,
                out=ResultRef[ClefChange](),
            )
        ],
    )
    engine.process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measure,
                position=MeasurePosition.of(numerator=1, denominator=2),
                staff=score.staff_a,
                clef=Clef.BASS,
                out=ResultRef[ClefChange](),
            )
        ],
    )

    assert len(score.measure.anchors) == 2
    assert [ctx.clef for anchor in score.measure.anchors for ctx in anchor.starting_contexts] == [
        Clef.TREBLE,
        Clef.BASS,
    ]
