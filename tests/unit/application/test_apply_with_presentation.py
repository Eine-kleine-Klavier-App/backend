import pytest
from tests.fixtures.drafts import in_memory_history
from tests.unit.domain.document_builders import score

from piano_app.application.errors import ScoreEditRejectedError
from piano_app.application.use_cases.score.edit.service import ScoreEditService
from piano_app.domain.score.document.models.context import Slur
from piano_app.domain.score.document.models.presentation import (
    PresentationTarget,
    ReferencePoint,
    VerticalOffset,
)
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import (
    CreateSlurIntent,
    MoveContextEndIntent,
    PitchEditMode,
)
from piano_app.domain.score.document.services.presentation import SetVerticalOffset

_START = MeasurePosition.of(numerator=0, denominator=1)
_BEAT_TWO = MeasurePosition.of(numerator=1, denominator=4)


def _slur_of(document):
    return next(
        context
        for measure in document.measures
        for anchor in measure.anchors
        for context in anchor.starting_contexts
        if isinstance(context, Slur)
    )


async def _service_with_a_slur():
    document = score()
    history = in_memory_history()
    draft = await history.create(
        title="slur", author_id="owner", ref_score_id=None, document=document
    )
    service = ScoreEditService(engine=build_engine(), compiler=build_compiler(), history=history)
    await service.apply(
        draft_id=draft.draft_id,
        actor_id="owner",
        intent=CreateSlurIntent(
            start_measure_id=document.measures[1].id,
            start_position=_START,
            end_measure_id=document.measures[2].id,
            end_position=_START,
            voice_ids=(document.voices[0].id,),
        ),
    )
    stored = await history.get(draft_id=draft.draft_id)
    return service, history, draft.draft_id, stored.document, _slur_of(stored.document)


def _move_end(*, document, slur) -> MoveContextEndIntent:
    return MoveContextEndIntent(
        context_id=slur.id,
        measure_id=document.measures[2].id,
        position=_BEAT_TWO,
        mode=PitchEditMode.PRESERVE_STEP,
    )


async def test_an_edge_move_and_the_height_it_freezes_are_one_gesture_and_one_undo():
    service, history, draft_id, document, slur = await _service_with_a_slur()
    height = PresentationTarget(entity_id=slur.id, reference=ReferencePoint.HEIGHT)

    state = await service.apply(
        draft_id=draft_id,
        actor_id="owner",
        intent=_move_end(document=document, slur=slur),
        presentation=[SetVerticalOffset(target=height, value=VerticalOffset(value=2.5))],
    )

    assert _slur_of((await history.get(draft_id=draft_id)).document).end.position == _BEAT_TWO
    assert state.view.jsonify()["presentation"]["vertical"] == [
        {"entity_id": slur.id, "reference": "height", "offset": 2.5}
    ]

    undone = await service.undo(draft_id=draft_id, actor_id="owner")

    assert _slur_of((await history.get(draft_id=draft_id)).document).end.position == _START
    assert undone.view.jsonify()["presentation"]["vertical"] == []


async def test_a_refused_presentation_command_leaves_the_move_undone_too():
    service, history, draft_id, document, slur = await _service_with_a_slur()
    missing = PresentationTarget(entity_id="missing", reference=ReferencePoint.HEIGHT)

    with pytest.raises(ScoreEditRejectedError):
        await service.apply(
            draft_id=draft_id,
            actor_id="owner",
            intent=_move_end(document=document, slur=slur),
            presentation=[SetVerticalOffset(target=missing, value=VerticalOffset(value=1))],
        )

    assert _slur_of((await history.get(draft_id=draft_id)).document).end.position == _START
    assert not (await history.get(draft_id=draft_id)).document.presentation.vertical
