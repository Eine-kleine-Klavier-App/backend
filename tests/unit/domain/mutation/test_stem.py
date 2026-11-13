from fractions import Fraction

import pytest
from tests.unit.domain.scene import build_score, note_at, quarters, snapshot

from piano_app.domain.score.document.models.notation import StemDirection
from piano_app.domain.score.document.models.presentation import (
    PresentationTarget,
    ReferencePoint,
    VerticalOffset,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.presentation import (
    PresentationEditor,
    SetDirection,
    SetVerticalOffset,
)


def test_stem_direction_and_tip_are_one_reversible_visual_batch():
    score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    carrier = note_at(score=score, at=Fraction(0)).note_carrier
    target = PresentationTarget(entity_id=carrier.id, reference=ReferencePoint.STEM_TIP)
    before = snapshot(score=score)
    revision = score.document.music_revision
    log = MutationLog()
    PresentationEditor().apply(
        document=score.document,
        commands=[
            SetDirection(target=target, value=StemDirection.DOWN),
            SetVerticalOffset(target=target, value=VerticalOffset(value=1.25)),
        ],
        sink=log,
    )
    assert not hasattr(carrier, "stem")
    assert score.document.presentation.vertical[target].value == 1.25
    assert score.document.presentation.directions[target] is StemDirection.DOWN
    assert snapshot(score=score) == before
    assert score.document.music_revision == revision
    log.rollback()
    assert not score.document.presentation.vertical and not score.document.presentation.directions
    log.reapply()
    assert score.document.presentation.vertical[target].value == 1.25


@pytest.mark.parametrize("value", [float("inf"), -float("inf"), float("nan")])
def test_stem_offsets_must_be_finite(value):
    with pytest.raises(ValueError):
        VerticalOffset(value=value)
