from fractions import Fraction
from unittest.mock import Mock

import pytest
from tests.unit.domain.scene import four_quarters, note_at, snapshot

from piano_app.adapters.outbound.in_memory.draft_history import InMemoryDraftHistory
from piano_app.application.use_cases.score.edit.service import ScoreEditService
from piano_app.domain.score.document.models.presentation import (
    EndpointOffsets,
    PresentationTarget,
    ReferencePoint,
    VerticalOffset,
)
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import (
    DeleteBatchIntent,
    ShiftStaffStepsIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.presentation import (
    PresentationEditor,
    SetEndpointOffsets,
    SetVerticalOffset,
)


def test_invalid_later_command_rejects_whole_batch_without_mutation():
    score = four_quarters()
    carrier = note_at(score=score, at=Fraction(0)).note_carrier
    log = MutationLog()
    with pytest.raises(ValueError):
        PresentationEditor().apply(
            document=score.document,
            commands=[
                SetVerticalOffset(
                    target=PresentationTarget(
                        entity_id=carrier.id, reference=ReferencePoint.STEM_TIP
                    ),
                    value=VerticalOffset(value=1.5),
                ),
                SetEndpointOffsets(
                    target=PresentationTarget(entity_id=carrier.id), value=EndpointOffsets(left=1)
                ),
            ],
            sink=log,
        )
    assert not log.has_changes and not score.document.presentation.vertical


@pytest.mark.parametrize("reference", [ReferencePoint.BODY, ReferencePoint.STEM_TIP])
def test_unknown_target_is_refused_even_when_resetting(reference):
    score = four_quarters()
    with pytest.raises(ValueError):
        PresentationEditor().apply(
            document=score.document,
            commands=[
                SetVerticalOffset(
                    target=PresentationTarget(entity_id="missing", reference=reference), value=None
                )
            ],
            sink=MutationLog(),
        )


async def test_visual_path_bypasses_music_engine_and_shares_history_and_revision():
    score = four_quarters()
    n = note_at(score=score, at=Fraction(0))
    target = PresentationTarget(entity_id=n.note_carrier.id, reference=ReferencePoint.STEM_TIP)
    history = InMemoryDraftHistory()
    draft = await history.create(
        title="presentation", author_id="owner", ref_score_id=None, document=score.document
    )
    engine = Mock()
    engine.transaction.side_effect = AssertionError("Visual edit entered musical pipeline")
    service = ScoreEditService(engine=engine, compiler=build_compiler(), history=history)
    before = snapshot(score=score)
    result = await service.apply_presentation(
        draft_id=draft.draft_id,
        actor_id="owner",
        commands=[SetVerticalOffset(target=target, value=VerticalOffset(value=1.5))],
    )
    assert result.jsonify()["music_revision"] == score.document.music_revision
    assert snapshot(score=score) == before
    undone = await service.undo(draft_id=draft.draft_id, actor_id="owner")
    assert not undone.jsonify()["presentation"]["vertical"]
    redone = await service.redo(draft_id=draft.draft_id, actor_id="owner")
    assert redone.jsonify()["presentation"]["vertical"][0]["offset"] == 1.5
    assert redone.jsonify()["music_revision"] == score.document.music_revision
    engine.transaction.assert_not_called()


async def test_music_change_rotates_revision_and_deletion_prunes_in_same_history_step():
    score = four_quarters()
    n = note_at(score=score, at=Fraction(0))
    target = PresentationTarget(entity_id=n.note_carrier.id, reference=ReferencePoint.STEM_TIP)
    history = InMemoryDraftHistory()
    draft = await history.create(
        title="presentation", author_id="owner", ref_score_id=None, document=score.document
    )
    service = ScoreEditService(engine=build_engine(), compiler=build_compiler(), history=history)
    await service.apply_presentation(
        draft_id=draft.draft_id,
        actor_id="owner",
        commands=[SetVerticalOffset(target=target, value=VerticalOffset(value=1.5))],
    )
    shifted = await service.apply(
        draft_id=draft.draft_id,
        actor_id="owner",
        intent=ShiftStaffStepsIntent(note_ids=(n.id,), delta=1),
    )
    changed_revision = shifted.jsonify()["music_revision"]
    assert changed_revision != score.document.music_revision
    assert shifted.jsonify()["presentation"]["vertical"]
    await service.undo(draft_id=draft.draft_id, actor_id="owner")
    branch = await service.apply(
        draft_id=draft.draft_id,
        actor_id="owner",
        intent=ShiftStaffStepsIntent(note_ids=(n.id,), delta=-1),
    )
    assert branch.jsonify()["music_revision"] not in (
        score.document.music_revision,
        changed_revision,
    )
    deleted = await service.apply(
        draft_id=draft.draft_id,
        actor_id="owner",
        intent=DeleteBatchIntent(entity_ids=(n.note_carrier.id,)),
    )
    assert not deleted.jsonify()["presentation"]["vertical"]
    restored = await service.undo(draft_id=draft.draft_id, actor_id="owner")
    assert restored.jsonify()["presentation"]["vertical"]
    assert restored.jsonify()["music_revision"] == branch.jsonify()["music_revision"]
