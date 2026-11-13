from fractions import Fraction

from tests.unit.domain.scene import four_quarters, note_at

from piano_app.domain.score.document.models.presentation import (
    PresentationTarget,
    ReferencePoint,
    VerticalOffset,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.presentation import (
    PresentationEditor,
    SetVerticalOffset,
)


def test_resetting_an_automatic_stem_is_a_noop():
    score = four_quarters()
    carrier = note_at(score=score, at=Fraction(0)).note_carrier
    target = PresentationTarget(entity_id=carrier.id, reference=ReferencePoint.STEM_TIP)
    log = MutationLog()
    PresentationEditor().apply(
        document=score.document, commands=[SetVerticalOffset(target=target, value=None)], sink=log
    )
    assert not log.has_changes


def test_multiple_stems_reset_in_one_reversible_batch():
    score = four_quarters()
    targets = [
        PresentationTarget(
            entity_id=note_at(score=score, at=Fraction(beat, 4)).note_carrier.id,
            reference=ReferencePoint.STEM_TIP,
        )
        for beat in (0, 2)
    ]
    editor = PresentationEditor()
    editor.apply(
        document=score.document,
        commands=[
            SetVerticalOffset(target=target, value=VerticalOffset(value=1.5)) for target in targets
        ],
        sink=MutationLog(),
    )
    log = MutationLog()
    editor.apply(
        document=score.document,
        commands=[SetVerticalOffset(target=target, value=None) for target in targets],
        sink=log,
    )
    assert not score.document.presentation.vertical
    log.rollback()
    assert set(score.document.presentation.vertical) == set(targets)
