from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path

from piano_app.adapters.inbound.http.current_user import CurrentUser
from piano_app.application.use_cases.score import ScoreEditService
from piano_app.application.use_cases.score.shared import ScoreView

from .requests import (
    AddContextVoiceRequest,
    AddGraceCarrierNoteRequest,
    AddGraceNoteRequest,
    AddRefrainEndingRequest,
    AppendVoltaFragmentRequest,
    ChangeDurationRequest,
    ChangeGraceTypeRequest,
    ChangeGraceValueRequest,
    ChangePitchRequest,
    ChangeTimeSignatureRequest,
    CreateBeamRequest,
    CreateHairpinRequest,
    CreateOctaveTranspositionRequest,
    CreateRefrainRequest,
    CreateSlurRequest,
    CreateSustainHoldRequest,
    CreateTempoTransitionRequest,
    CreateTupletRequest,
    CreateVoltaRequest,
    DeleteBatchRequest,
    DeleteClefRequest,
    DeleteOctaveTranspositionRequest,
    EditPresentationRequest,
    GlissandoNotesRequest,
    InsertMeasureRequest,
    InsertNoteRequest,
    InsertRestRequest,
    MoveContextEndRequest,
    MoveContextStartRequest,
    MoveNoteToStaffRequest,
    MoveRefrainEndRequest,
    MoveRefrainStartRequest,
    MoveVoltaBoundaryRequest,
    MoveVoltaStartRequest,
    OpenContextEndRequest,
    RemoveContextVoiceRequest,
    RemoveGraceNoteRequest,
    SetAccidentalRequest,
    SetArticulationRequest,
    SetCarrierMarksRequest,
    SetClefRequest,
    SetDynamicRequest,
    SetFingeringRequest,
    SetHairpinTargetRequest,
    SetKeySignatureRequest,
    SetOrnamentRequest,
    SetRefrainTimesRequest,
    SetTempoRequest,
    SetTempoTransitionTargetRequest,
    SetVoltaFragmentPassesRequest,
    SetVoltaTimesRequest,
    ShiftStaffStepsRequest,
    SplitBeamRequest,
    SplitVoltaFragmentRequest,
    TieNotesRequest,
    ToggleArticulationRequest,
)
from .responses import ScoreEditedResponse


def build_edit_router(*, service: ScoreEditService, current_user: CurrentUser) -> APIRouter:
    router: APIRouter = APIRouter(
        prefix="/drafts/{draft_id}/edit",
        tags=["score-edit"],
    )

    @router.put(path="/presentation", status_code=200)
    async def edit_presentation(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[EditPresentationRequest, Body()],
    ) -> ScoreEditedResponse:
        view = await service.apply_presentation(
            draft_id=draft_id, actor_id=actor_id, commands=request.to_commands()
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/notes", status_code=200)
    async def insert_note(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[InsertNoteRequest, Body(description="The insert command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/grace-notes", status_code=200)
    async def add_grace_note(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[AddGraceNoteRequest, Body(description="The grace note command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/grace-carrier-notes", status_code=200)
    async def add_grace_carrier_note(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[AddGraceCarrierNoteRequest, Body(description="The note command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/grace-value-changes", status_code=200)
    async def change_grace_value(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[ChangeGraceValueRequest, Body(description="The change command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/grace-type-changes", status_code=200)
    async def change_grace_type(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[ChangeGraceTypeRequest, Body(description="The change command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/grace-note-removals", status_code=200)
    async def remove_grace_note(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[RemoveGraceNoteRequest, Body(description="The removal command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/rests", status_code=200)
    async def insert_rest(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[InsertRestRequest, Body(description="The insert command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/tuplets", status_code=200)
    async def create_tuplet(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[CreateTupletRequest, Body(description="The tuplet command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/glissandos", status_code=200)
    async def glissando_notes(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[GlissandoNotesRequest, Body(description="The glissando command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/ties", status_code=200)
    async def tie_notes(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[TieNotesRequest, Body(description="The tie command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/beams", status_code=200)
    async def create_beam(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[CreateBeamRequest, Body(description="The beam command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/beams/split", status_code=200)
    async def split_beam(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[SplitBeamRequest, Body(description="The beam split command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/batch-delete", status_code=200)
    async def delete_batch(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[DeleteBatchRequest, Body(description="The delete command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/fingerings", status_code=200)
    async def set_fingering(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[SetFingeringRequest, Body(description="The fingering command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/articulations", status_code=200)
    async def set_articulation(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[SetArticulationRequest, Body(description="The articulation command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/articulation-toggles", status_code=200)
    async def toggle_articulation(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[ToggleArticulationRequest, Body(description="The toggle command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/ornaments", status_code=200)
    async def set_ornament(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[SetOrnamentRequest, Body(description="The ornament command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/carrier-marks", status_code=200)
    async def set_carrier_marks(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[SetCarrierMarksRequest, Body(description="The marks of the carriers")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/durations", status_code=200)
    async def change_duration(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[ChangeDurationRequest, Body(description="The duration command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/measures", status_code=200)
    async def insert_measure(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[InsertMeasureRequest, Body(description="The measure command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/time-signatures", status_code=200)
    async def change_time_signature(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[
            ChangeTimeSignatureRequest, Body(description="The time signature command")
        ],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/tempos", status_code=200)
    async def set_tempo(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[SetTempoRequest, Body(description="The tempo command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/tempo-transitions", status_code=200)
    async def create_tempo_transition(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[
            CreateTempoTransitionRequest, Body(description="The tempo transition command")
        ],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/tempo-transition-targets", status_code=200)
    async def set_tempo_transition_target(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[
            SetTempoTransitionTargetRequest, Body(description="The new target tempo")
        ],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/dynamics", status_code=200)
    async def set_dynamic(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[SetDynamicRequest, Body(description="The dynamic command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/context-voices", status_code=200)
    async def add_context_voice(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[AddContextVoiceRequest, Body(description="The voice to add")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/context-voice-removals", status_code=200)
    async def remove_context_voice(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[RemoveContextVoiceRequest, Body(description="The voice to remove")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/hairpins", status_code=200)
    async def create_hairpin(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[CreateHairpinRequest, Body(description="The hairpin command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/hairpin-targets", status_code=200)
    async def set_hairpin_target(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[SetHairpinTargetRequest, Body(description="The new target dynamic")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/key-signatures", status_code=200)
    async def set_key_signature(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[SetKeySignatureRequest, Body(description="The key signature command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/slurs", status_code=200)
    async def create_slur(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[CreateSlurRequest, Body(description="The slur command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/refrains", status_code=200)
    async def create_refrain(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[CreateRefrainRequest, Body(description="The refrain command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/refrain-times", status_code=200)
    async def set_refrain_times(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[
            SetRefrainTimesRequest, Body(description="How many times the refrain is played")
        ],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/refrain-starts", status_code=200)
    async def move_refrain_start(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[MoveRefrainStartRequest, Body(description="Where the refrain starts")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/refrain-ends", status_code=200)
    async def move_refrain_end(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[MoveRefrainEndRequest, Body(description="Where the refrain ends")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/voltas", status_code=200)
    async def create_volta(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[CreateVoltaRequest, Body(description="The volta command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/volta-boundaries", status_code=200)
    async def move_volta_boundary(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[
            MoveVoltaBoundaryRequest, Body(description="The boundary of the volta to move")
        ],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/volta-starts", status_code=200)
    async def move_volta_start(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[
            MoveVoltaStartRequest, Body(description="Where the body of the volta starts")
        ],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/volta-fragment-passes", status_code=200)
    async def set_volta_fragment_passes(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[
            SetVoltaFragmentPassesRequest, Body(description="The passes of a fragment")
        ],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/volta-times", status_code=200)
    async def set_volta_times(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[
            SetVoltaTimesRequest, Body(description="How many times a volta is played")
        ],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/volta-fragments", status_code=200)
    async def append_volta_fragment(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[
            AppendVoltaFragmentRequest, Body(description="A fragment after the last one")
        ],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/volta-fragment-splits", status_code=200)
    async def split_volta_fragment(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[
            SplitVoltaFragmentRequest, Body(description="Where to cut the last fragment")
        ],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/refrain-endings", status_code=200)
    async def add_refrain_ending(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[
            AddRefrainEndingRequest, Body(description="The first ending of a repeat")
        ],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/context-open-ends", status_code=200)
    async def open_context_end(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[
            OpenContextEndRequest, Body(description="The span to last until the end of the score")
        ],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/sustain-holds", status_code=200)
    async def create_sustain_hold(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[CreateSustainHoldRequest, Body(description="The sustain hold command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/octave-transpositions", status_code=200)
    async def create_octave_transposition(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[
            CreateOctaveTranspositionRequest, Body(description="The octave transposition command")
        ],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/context-starts", status_code=200)
    async def move_context_start(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[
            MoveContextStartRequest, Body(description="The new start of the context")
        ],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
            presentation=request.to_presentation(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/context-ends", status_code=200)
    async def move_context_end(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[MoveContextEndRequest, Body(description="The new end of the context")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
            presentation=request.to_presentation(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/clefs", status_code=200)
    async def set_clef(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[SetClefRequest, Body(description="The clef command")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/clef-deletions", status_code=200)
    async def delete_clef(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[DeleteClefRequest, Body(description="The clef to take out")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/octave-transposition-deletions", status_code=200)
    async def delete_octave_transposition(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[
            DeleteOctaveTranspositionRequest, Body(description="The line to delete")
        ],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/pitches/shift", status_code=200)
    async def shift_staff_steps(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: ShiftStaffStepsRequest,
    ) -> ScoreEditedResponse:
        view = await service.apply(draft_id=draft_id, actor_id=actor_id, intent=request.to_intent())
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/pitches", status_code=200)
    async def change_pitch(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[ChangePitchRequest, Body(description="The new step of the note")],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/accidentals", status_code=200)
    async def set_accidental(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[
            SetAccidentalRequest, Body(description="The new accidental of the note")
        ],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.put(path="/note-staffs", status_code=200)
    async def move_note_to_staff(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
        request: Annotated[
            MoveNoteToStaffRequest, Body(description="The staff to move the note to")
        ],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.apply(
            draft_id=draft_id,
            actor_id=actor_id,
            intent=request.to_intent(),
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/undo", status_code=200)
    async def undo(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.undo(
            draft_id=draft_id,
            actor_id=actor_id,
        )
        return ScoreEditedResponse.from_view(view)

    @router.post(path="/redo", status_code=200)
    async def redo(
        draft_id: Annotated[str, Path(description="The draft ID")],
        actor_id: Annotated[str, Depends(current_user)],
    ) -> ScoreEditedResponse:
        view: ScoreView = await service.redo(
            draft_id=draft_id,
            actor_id=actor_id,
        )
        return ScoreEditedResponse.from_view(view)

    return router
