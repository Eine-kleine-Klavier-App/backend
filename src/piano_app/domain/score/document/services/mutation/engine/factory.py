from collections.abc import Callable

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation.engine.analyzers.context import (
    AppendVoltaFragmentAnalyzer,
    ClearContextsAnalyzer,
    CloseOpenContextEndsAnalyzer,
    CollapseRefrainAnalyzer,
    CollapseVoltaAnalyzer,
    CreateClefChangeAnalyzer,
    CreateDynamicChangeAnalyzer,
    CreateHairpinAnalyzer,
    CreateKeySignatureChangeAnalyzer,
    CreateOctaveTranspositionAnalyzer,
    CreateRefrainAnalyzer,
    CreateSlurAnalyzer,
    CreateSustainHoldAnalyzer,
    CreateTempoChangeAnalyzer,
    CreateTempoTransitionAnalyzer,
    CreateVoltaAnalyzer,
    KeepContextEndsAnalyzer,
    MoveRefrainEndAnalyzer,
    MoveRefrainStartAnalyzer,
    MoveVoltaBoundaryAnalyzer,
    MoveVoltaStartAnalyzer,
    OpenContextEndAnalyzer,
    SetVoltaFragmentPassesAnalyzer,
    SetVoltaTimesAnalyzer,
    SplitVoltaFragmentAnalyzer,
    UpdateContextEndAnalyzer,
    UpdateContextStartAnalyzer,
    UpdateHairpinStepsAnalyzer,
    UpdateRefrainTimesAnalyzer,
    UpdateTempoTransitionRatioAnalyzer,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.delete import (
    DeleteAnalyzer,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.intent import (
    AddGraceNoteAnalyzer,
    ChangeTimeSignatureAnalyzer,
    InsertMeasureAnalyzer,
    PreservePitchAnalyzer,
    RemoveAnalyzer,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.material import (
    CreateNoteAnalyzer,
    CreateNoteCarrierAnalyzer,
    CreateRestAnalyzer,
    CreateRestCarrierAnalyzer,
    UpdateArticulationAnalyzer,
    UpdateFingeringAnalyzer,
    UpdateNotePitchAnalyzer,
    UpdateOrnamentAnalyzer,
    UpdateStaffStepAnalyzer,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.relations import (
    AddBeamMemberAnalyzer,
    CheckRelationAnalyzer,
    CreateBeamAnalyzer,
    CreateGlissandoAnalyzer,
    CreateTieAnalyzer,
    SplitBeamAnalyzer,
    UpdateBeamMembersAnalyzer,
    UpdateRelationStartAnalyzer,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.rhythmic import (
    CreateGraceGroupAnalyzer,
    CreateGraceItemAnalyzer,
    CreateLeafAnalyzer,
    CreateRhythmicGroupAnalyzer,
    CutAtBarlinesAnalyzer,
    PlaceSpansAnalyzer,
    ResizeSpanAnalyzer,
    SplitRhythmicGroupAnalyzer,
    UpdateGraceTypeAnalyzer,
    UpdateGraceValueAnalyzer,
    UpdateLeafSizeAnalyzer,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.structural import (
    CreateEmptyMeasureAnalyzer,
    DeleteEmptyMeasureAnalyzer,
    RebarMeasuresAnalyzer,
    UpdateMeasureTimeSignatureAnalyzer,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.temporal import (
    CreateTemporalAnchorAnalyzer,
    UpdateTemporalAnchorAnalyzer,
)
from piano_app.domain.score.document.services.mutation.engine.engine import MutationEngine
from piano_app.domain.score.document.services.mutation.engine.guards import RelationGuard
from piano_app.domain.score.document.services.mutation.engine.guards.jump_elements import (
    JumpElementsGuard,
)
from piano_app.domain.score.document.services.mutation.engine.handlers.context import (
    CreateClefChangeHandler,
    CreateDynamicChangeHandler,
    CreateHairpinHandler,
    CreateKeySignatureChangeHandler,
    CreateOctaveTranspositionHandler,
    CreateRefrainHandler,
    CreateSlurHandler,
    CreateSustainHoldHandler,
    CreateTempoChangeHandler,
    CreateTempoTransitionHandler,
    CreateVoltaHandler,
    DeleteContextHandler,
    ReshapeVoltaHandler,
    UpdateContextEndHandler,
    UpdateContextStartHandler,
    UpdateHairpinStepsHandler,
    UpdateRefrainEndHandler,
    UpdateRefrainStartHandler,
    UpdateRefrainTimesHandler,
    UpdateTempoTransitionRatioHandler,
)
from piano_app.domain.score.document.services.mutation.engine.handlers.material import (
    CreateNoteCarrierHandler,
    CreateNoteHandler,
    CreateRestCarrierHandler,
    CreateRestHandler,
    DeleteNoteCarrierHandler,
    DeleteNoteHandler,
    DeleteRestCarrierHandler,
    DeleteRestHandler,
    UpdateArticulationHandler,
    UpdateFingeringHandler,
    UpdateNotePitchHandler,
    UpdateOrnamentHandler,
    UpdateStaffStepHandler,
)
from piano_app.domain.score.document.services.mutation.engine.handlers.relations import (
    AddBeamMemberHandler,
    CreateBeamHandler,
    CreateGlissandoHandler,
    CreateTieHandler,
    DeleteRelationHandler,
    UpdateBeamMembersHandler,
    UpdateRelationStartHandler,
)
from piano_app.domain.score.document.services.mutation.engine.handlers.rhythmic import (
    CreateGraceGroupHandler,
    CreateGraceItemHandler,
    CreateLeafHandler,
    CreateRhythmicGroupHandler,
    DeleteGraceGroupHandler,
    DeleteGraceItemHandler,
    DeleteLeafHandler,
    DeleteRhythmicGroupHandler,
    SplitRhythmicGroupHandler,
    UpdateGraceTypeHandler,
    UpdateGraceValueHandler,
    UpdateLeafSizeHandler,
)
from piano_app.domain.score.document.services.mutation.engine.handlers.structural import (
    CreateMeasureHandler,
    DeleteMeasureHandler,
    UpdateMeasureTimeSignatureHandler,
)
from piano_app.domain.score.document.services.mutation.engine.handlers.temporal import (
    CreateTemporalAnchorHandler,
    DeleteTemporalAnchorHandler,
    UpdateTemporalAnchorHandler,
)
from piano_app.domain.score.document.services.mutation.engine.postprocessors import (
    EmptyGroupsPostprocessor,
    EmptyLeavesPostprocessor,
    FillGapsPostprocessor,
    MutatedStatePostprocessor,
    OrphanAnchorsPostprocessor,
    PitchPostprocessor,
    PitchRelationsPostprocessor,
)
from piano_app.domain.score.document.services.mutation.engine.registry import (
    MutationAnalyzerRegistry,
    MutationHandlerRegistry,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateClefChangeAction,
    CreateDynamicChangeAction,
    CreateHairpinAction,
    CreateKeySignatureChangeAction,
    CreateOctaveTranspositionAction,
    CreateRefrainAction,
    CreateSlurAction,
    CreateSustainHoldAction,
    CreateTempoChangeAction,
    CreateTempoTransitionAction,
    CreateVoltaAction,
    DeleteContextAction,
    ReshapeVoltaAction,
    UpdateContextEndAction,
    UpdateContextStartAction,
    UpdateHairpinStepsAction,
    UpdateRefrainEndAction,
    UpdateRefrainStartAction,
    UpdateRefrainTimesAction,
    UpdateTempoTransitionRatioAction,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.material import (
    CreateNoteAction,
    CreateNoteCarrierAction,
    CreateRestAction,
    CreateRestCarrierAction,
    DeleteNoteAction,
    DeleteNoteCarrierAction,
    DeleteRestAction,
    DeleteRestCarrierAction,
    UpdateArticulationAction,
    UpdateFingeringAction,
    UpdateNotePitchAction,
    UpdateOrnamentAction,
    UpdateStaffStepAction,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.relations import (
    AddBeamMemberAction,
    CreateBeamAction,
    CreateGlissandoAction,
    CreateTieAction,
    DeleteRelationAction,
    UpdateBeamMembersAction,
    UpdateRelationStartAction,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.rhythmic import (
    CreateGraceGroupAction,
    CreateGraceItemAction,
    CreateLeafAction,
    CreateRhythmicGroupAction,
    DeleteGraceGroupAction,
    DeleteGraceItemAction,
    DeleteLeafAction,
    DeleteRhythmicGroupAction,
    SplitRhythmicGroupAction,
    UpdateGraceTypeAction,
    UpdateGraceValueAction,
    UpdateLeafSizeAction,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.structural import (
    CreateMeasureAction,
    DeleteMeasureAction,
    UpdateMeasureTimeSignatureAction,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.temporal import (
    CreateTemporalAnchorAction,
    DeleteTemporalAnchorAction,
    UpdateTemporalAnchorAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    AppendVoltaFragmentRequest,
    ClearContextsRequest,
    CloseOpenContextEndsRequest,
    CollapseRefrainRequest,
    CollapseVoltaRequest,
    CreateClefChangeRequest,
    CreateDynamicChangeRequest,
    CreateHairpinRequest,
    CreateKeySignatureChangeRequest,
    CreateOctaveTranspositionRequest,
    CreateRefrainRequest,
    CreateSlurRequest,
    CreateSustainHoldRequest,
    CreateTempoChangeRequest,
    CreateTempoTransitionRequest,
    CreateVoltaRequest,
    KeepContextEndsRequest,
    MoveRefrainEndRequest,
    MoveRefrainStartRequest,
    MoveVoltaBoundaryRequest,
    MoveVoltaStartRequest,
    OpenContextEndRequest,
    SetVoltaFragmentPassesRequest,
    SetVoltaTimesRequest,
    SplitVoltaFragmentRequest,
    UpdateContextEndRequest,
    UpdateContextStartRequest,
    UpdateHairpinStepsRequest,
    UpdateRefrainTimesRequest,
    UpdateTempoTransitionRatioRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.intent import (
    AddGraceNoteRequest,
    ChangeTimeSignatureRequest,
    InsertMeasureRequest,
    PreservePitchRequest,
    RemoveRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    CreateNoteCarrierRequest,
    CreateNoteRequest,
    CreateRestCarrierRequest,
    CreateRestRequest,
    UpdateArticulationRequest,
    UpdateFingeringRequest,
    UpdateNotePitchRequest,
    UpdateOrnamentRequest,
    UpdateStaffStepRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    AddBeamMemberRequest,
    CheckRelationRequest,
    CreateBeamRequest,
    CreateGlissandoRequest,
    CreateTieRequest,
    SplitBeamRequest,
    UpdateBeamMembersRequest,
    UpdateRelationStartRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    CreateGraceGroupRequest,
    CreateGraceItemRequest,
    CreateLeafRequest,
    CreateRhythmicGroupRequest,
    CutAtBarlinesRequest,
    PlaceSpansRequest,
    ResizeSpanRequest,
    SplitRhythmicGroupRequest,
    UpdateGraceTypeRequest,
    UpdateGraceValueRequest,
    UpdateLeafSizeRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.structural import (
    CreateEmptyMeasureRequest,
    DeleteEmptyMeasureRequest,
    RebarMeasuresRequest,
    UpdateMeasureTimeSignatureRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.temporal import (
    CreateTemporalAnchorRequest,
    UpdateTemporalAnchorRequest,
)
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch


def build_analyzer_registry() -> MutationAnalyzerRegistry:
    registry: MutationAnalyzerRegistry = MutationAnalyzerRegistry()

    registry.register(request_type=CreateNoteRequest, analyzer=CreateNoteAnalyzer())
    registry.register(request_type=DeleteRequest, analyzer=DeleteAnalyzer())
    registry.register(request_type=CreateRestRequest, analyzer=CreateRestAnalyzer())
    registry.register(
        request_type=CreateNoteCarrierRequest,
        analyzer=CreateNoteCarrierAnalyzer(),
    )
    registry.register(
        request_type=CreateRestCarrierRequest,
        analyzer=CreateRestCarrierAnalyzer(),
    )
    registry.register_pitch(request_type=CreateTieRequest, analyzer=CreateTieAnalyzer())
    registry.register(request_type=CreateGlissandoRequest, analyzer=CreateGlissandoAnalyzer())
    registry.register(request_type=CreateLeafRequest, analyzer=CreateLeafAnalyzer())
    registry.register(
        request_type=CreateRhythmicGroupRequest,
        analyzer=CreateRhythmicGroupAnalyzer(),
    )
    registry.register_pitch(request_type=PlaceSpansRequest, analyzer=PlaceSpansAnalyzer())
    registry.register_pitch(request_type=ResizeSpanRequest, analyzer=ResizeSpanAnalyzer())
    registry.register(request_type=UpdateLeafSizeRequest, analyzer=UpdateLeafSizeAnalyzer())
    registry.register(
        request_type=CreateTemporalAnchorRequest,
        analyzer=CreateTemporalAnchorAnalyzer(),
    )
    registry.register_contexts(
        request_type=CreateClefChangeRequest,
        analyzer=CreateClefChangeAnalyzer(),
    )
    registry.register_contexts(
        request_type=CreateKeySignatureChangeRequest,
        analyzer=CreateKeySignatureChangeAnalyzer(),
    )
    registry.register_contexts(
        request_type=CreateOctaveTranspositionRequest,
        analyzer=CreateOctaveTranspositionAnalyzer(),
    )
    registry.register(
        request_type=UpdateFingeringRequest,
        analyzer=UpdateFingeringAnalyzer(),
    )
    registry.register(request_type=UpdateStaffStepRequest, analyzer=UpdateStaffStepAnalyzer())
    registry.register_pitch(request_type=UpdateNotePitchRequest, analyzer=UpdateNotePitchAnalyzer())
    registry.register(
        request_type=UpdateArticulationRequest,
        analyzer=UpdateArticulationAnalyzer(),
    )
    registry.register(request_type=UpdateOrnamentRequest, analyzer=UpdateOrnamentAnalyzer())
    registry.register(request_type=RemoveRequest, analyzer=RemoveAnalyzer())
    registry.register(request_type=InsertMeasureRequest, analyzer=InsertMeasureAnalyzer())
    registry.register(request_type=AddGraceNoteRequest, analyzer=AddGraceNoteAnalyzer())
    registry.register(request_type=CreateGraceGroupRequest, analyzer=CreateGraceGroupAnalyzer())
    registry.register(request_type=CreateGraceItemRequest, analyzer=CreateGraceItemAnalyzer())
    registry.register(request_type=UpdateGraceTypeRequest, analyzer=UpdateGraceTypeAnalyzer())
    registry.register(request_type=UpdateGraceValueRequest, analyzer=UpdateGraceValueAnalyzer())
    registry.register_pitch(request_type=PreservePitchRequest, analyzer=PreservePitchAnalyzer())
    registry.register(
        request_type=UpdateBeamMembersRequest,
        analyzer=UpdateBeamMembersAnalyzer(),
    )
    registry.register(request_type=CreateBeamRequest, analyzer=CreateBeamAnalyzer())
    registry.register(request_type=AddBeamMemberRequest, analyzer=AddBeamMemberAnalyzer())
    registry.register(request_type=SplitBeamRequest, analyzer=SplitBeamAnalyzer())
    registry.register(
        request_type=UpdateRelationStartRequest,
        analyzer=UpdateRelationStartAnalyzer(),
    )
    registry.register(
        request_type=SplitRhythmicGroupRequest,
        analyzer=SplitRhythmicGroupAnalyzer(),
    )
    registry.register_contexts(request_type=ClearContextsRequest, analyzer=ClearContextsAnalyzer())
    registry.register_contexts(
        request_type=UpdateContextStartRequest,
        analyzer=UpdateContextStartAnalyzer(),
    )
    registry.register_contexts(
        request_type=UpdateContextEndRequest,
        analyzer=UpdateContextEndAnalyzer(),
    )
    registry.register_contexts(
        request_type=OpenContextEndRequest,
        analyzer=OpenContextEndAnalyzer(),
    )
    registry.register_contexts(
        request_type=CloseOpenContextEndsRequest,
        analyzer=CloseOpenContextEndsAnalyzer(),
    )
    registry.register_contexts(
        request_type=CreateDynamicChangeRequest, analyzer=CreateDynamicChangeAnalyzer()
    )
    registry.register_contexts(request_type=CreateHairpinRequest, analyzer=CreateHairpinAnalyzer())
    registry.register(request_type=UpdateHairpinStepsRequest, analyzer=UpdateHairpinStepsAnalyzer())
    registry.register(request_type=CreateSlurRequest, analyzer=CreateSlurAnalyzer())
    registry.register_contexts(request_type=CreateRefrainRequest, analyzer=CreateRefrainAnalyzer())
    registry.register(request_type=UpdateRefrainTimesRequest, analyzer=UpdateRefrainTimesAnalyzer())
    registry.register_contexts(request_type=CreateVoltaRequest, analyzer=CreateVoltaAnalyzer())
    registry.register_contexts(
        request_type=CollapseRefrainRequest, analyzer=CollapseRefrainAnalyzer()
    )
    registry.register_contexts(request_type=CollapseVoltaRequest, analyzer=CollapseVoltaAnalyzer())
    registry.register_contexts(
        request_type=MoveRefrainStartRequest, analyzer=MoveRefrainStartAnalyzer()
    )
    registry.register_contexts(
        request_type=MoveRefrainEndRequest, analyzer=MoveRefrainEndAnalyzer()
    )
    registry.register_contexts(
        request_type=MoveVoltaBoundaryRequest, analyzer=MoveVoltaBoundaryAnalyzer()
    )
    registry.register_contexts(
        request_type=MoveVoltaStartRequest, analyzer=MoveVoltaStartAnalyzer()
    )
    registry.register_contexts(
        request_type=SetVoltaFragmentPassesRequest, analyzer=SetVoltaFragmentPassesAnalyzer()
    )
    registry.register_contexts(request_type=SetVoltaTimesRequest, analyzer=SetVoltaTimesAnalyzer())
    registry.register_contexts(
        request_type=AppendVoltaFragmentRequest, analyzer=AppendVoltaFragmentAnalyzer()
    )
    registry.register_contexts(
        request_type=SplitVoltaFragmentRequest, analyzer=SplitVoltaFragmentAnalyzer()
    )
    registry.register_contexts(
        request_type=CreateSustainHoldRequest, analyzer=CreateSustainHoldAnalyzer()
    )
    registry.register_contexts(
        request_type=CreateTempoChangeRequest, analyzer=CreateTempoChangeAnalyzer()
    )
    registry.register_contexts(
        request_type=CreateTempoTransitionRequest, analyzer=CreateTempoTransitionAnalyzer()
    )
    registry.register(
        request_type=UpdateTempoTransitionRatioRequest,
        analyzer=UpdateTempoTransitionRatioAnalyzer(),
    )
    registry.register(
        request_type=ChangeTimeSignatureRequest,
        analyzer=ChangeTimeSignatureAnalyzer(),
    )
    registry.register(request_type=RebarMeasuresRequest, analyzer=RebarMeasuresAnalyzer())
    registry.register(
        request_type=CreateEmptyMeasureRequest,
        analyzer=CreateEmptyMeasureAnalyzer(),
    )
    registry.register(
        request_type=DeleteEmptyMeasureRequest,
        analyzer=DeleteEmptyMeasureAnalyzer(),
    )
    registry.register(
        request_type=UpdateMeasureTimeSignatureRequest,
        analyzer=UpdateMeasureTimeSignatureAnalyzer(),
    )
    registry.register(
        request_type=UpdateTemporalAnchorRequest,
        analyzer=UpdateTemporalAnchorAnalyzer(),
    )
    registry.register(request_type=CutAtBarlinesRequest, analyzer=CutAtBarlinesAnalyzer())
    registry.register(request_type=KeepContextEndsRequest, analyzer=KeepContextEndsAnalyzer())
    registry.register(request_type=CheckRelationRequest, analyzer=CheckRelationAnalyzer())

    return registry


def build_handler_registry() -> MutationHandlerRegistry:
    registry: MutationHandlerRegistry = MutationHandlerRegistry()

    registry.register(action_type=CreateNoteAction, handler=CreateNoteHandler())
    registry.register(action_type=DeleteNoteAction, handler=DeleteNoteHandler())
    registry.register(action_type=CreateRestAction, handler=CreateRestHandler())
    registry.register(action_type=DeleteRestAction, handler=DeleteRestHandler())
    registry.register(action_type=CreateNoteCarrierAction, handler=CreateNoteCarrierHandler())
    registry.register(action_type=DeleteNoteCarrierAction, handler=DeleteNoteCarrierHandler())
    registry.register(action_type=CreateRestCarrierAction, handler=CreateRestCarrierHandler())
    registry.register(action_type=DeleteRestCarrierAction, handler=DeleteRestCarrierHandler())
    registry.register(action_type=CreateTieAction, handler=CreateTieHandler())
    registry.register(action_type=CreateGlissandoAction, handler=CreateGlissandoHandler())
    registry.register(action_type=DeleteRelationAction, handler=DeleteRelationHandler())
    registry.register(action_type=CreateLeafAction, handler=CreateLeafHandler())
    registry.register(action_type=CreateGraceGroupAction, handler=CreateGraceGroupHandler())
    registry.register(action_type=CreateGraceItemAction, handler=CreateGraceItemHandler())
    registry.register(action_type=DeleteGraceGroupAction, handler=DeleteGraceGroupHandler())
    registry.register(action_type=DeleteGraceItemAction, handler=DeleteGraceItemHandler())
    registry.register(action_type=UpdateGraceTypeAction, handler=UpdateGraceTypeHandler())
    registry.register(action_type=UpdateGraceValueAction, handler=UpdateGraceValueHandler())
    registry.register(action_type=DeleteLeafAction, handler=DeleteLeafHandler())
    registry.register(action_type=UpdateLeafSizeAction, handler=UpdateLeafSizeHandler())
    registry.register(action_type=CreateRhythmicGroupAction, handler=CreateRhythmicGroupHandler())
    registry.register(action_type=DeleteRhythmicGroupAction, handler=DeleteRhythmicGroupHandler())
    registry.register(action_type=CreateTemporalAnchorAction, handler=CreateTemporalAnchorHandler())
    registry.register(action_type=DeleteTemporalAnchorAction, handler=DeleteTemporalAnchorHandler())
    registry.register(action_type=CreateClefChangeAction, handler=CreateClefChangeHandler())
    registry.register(
        action_type=CreateKeySignatureChangeAction,
        handler=CreateKeySignatureChangeHandler(),
    )
    registry.register(
        action_type=CreateOctaveTranspositionAction,
        handler=CreateOctaveTranspositionHandler(),
    )
    registry.register(action_type=DeleteContextAction, handler=DeleteContextHandler())
    registry.register(action_type=UpdateFingeringAction, handler=UpdateFingeringHandler())
    registry.register(action_type=UpdateStaffStepAction, handler=UpdateStaffStepHandler())
    registry.register(action_type=UpdateNotePitchAction, handler=UpdateNotePitchHandler())
    registry.register(action_type=UpdateArticulationAction, handler=UpdateArticulationHandler())
    registry.register(action_type=UpdateOrnamentAction, handler=UpdateOrnamentHandler())
    registry.register(action_type=SplitRhythmicGroupAction, handler=SplitRhythmicGroupHandler())
    registry.register(action_type=UpdateBeamMembersAction, handler=UpdateBeamMembersHandler())
    registry.register(action_type=CreateBeamAction, handler=CreateBeamHandler())
    registry.register(action_type=AddBeamMemberAction, handler=AddBeamMemberHandler())
    registry.register(action_type=UpdateRelationStartAction, handler=UpdateRelationStartHandler())
    registry.register(action_type=CreateMeasureAction, handler=CreateMeasureHandler())
    registry.register(action_type=DeleteMeasureAction, handler=DeleteMeasureHandler())
    registry.register(action_type=UpdateContextStartAction, handler=UpdateContextStartHandler())
    registry.register(action_type=UpdateContextEndAction, handler=UpdateContextEndHandler())
    registry.register(action_type=CreateDynamicChangeAction, handler=CreateDynamicChangeHandler())
    registry.register(action_type=CreateHairpinAction, handler=CreateHairpinHandler())
    registry.register(action_type=UpdateHairpinStepsAction, handler=UpdateHairpinStepsHandler())
    registry.register(action_type=CreateSlurAction, handler=CreateSlurHandler())
    registry.register(action_type=CreateRefrainAction, handler=CreateRefrainHandler())
    registry.register(action_type=UpdateRefrainTimesAction, handler=UpdateRefrainTimesHandler())
    registry.register(action_type=CreateVoltaAction, handler=CreateVoltaHandler())
    registry.register(action_type=ReshapeVoltaAction, handler=ReshapeVoltaHandler())
    registry.register(action_type=UpdateRefrainStartAction, handler=UpdateRefrainStartHandler())
    registry.register(action_type=UpdateRefrainEndAction, handler=UpdateRefrainEndHandler())
    registry.register(action_type=CreateSustainHoldAction, handler=CreateSustainHoldHandler())
    registry.register(action_type=CreateTempoChangeAction, handler=CreateTempoChangeHandler())
    registry.register(
        action_type=CreateTempoTransitionAction, handler=CreateTempoTransitionHandler()
    )
    registry.register(
        action_type=UpdateTempoTransitionRatioAction, handler=UpdateTempoTransitionRatioHandler()
    )
    registry.register(
        action_type=UpdateMeasureTimeSignatureAction,
        handler=UpdateMeasureTimeSignatureHandler(),
    )
    registry.register(action_type=UpdateTemporalAnchorAction, handler=UpdateTemporalAnchorHandler())

    return registry


def build_postprocessors() -> list[MutatedStatePostprocessor]:
    # the order is the contract: each post leaves nothing an earlier one would act on
    return [
        EmptyLeavesPostprocessor(),
        EmptyGroupsPostprocessor(),
        FillGapsPostprocessor(),
        OrphanAnchorsPostprocessor(),
    ]


def build_pitch_postprocessors() -> list[PitchPostprocessor]:
    return [PitchRelationsPostprocessor()]


def build_engine(
    *,
    geometry_check: Callable[[ScoreGeometry, ScoreDocument], None] | None = None,
    checkpoint_geometry_check: Callable[[ScoreGeometry, ScoreDocument], None] | None = None,
    checkpoint_pitch_check: Callable[[ScorePitch, ScoreGeometry, ScoreDocument], None]
    | None = None,
    checkpoint_entities_check: Callable[[EntityIndex, ScoreDocument], None] | None = None,
) -> MutationEngine:
    """The engine; production sets no checks, tests set them."""
    return MutationEngine(
        handler_registry=build_handler_registry(),
        analyzer_registry=build_analyzer_registry(),
        postprocessors=build_postprocessors(),
        guards=[RelationGuard(), JumpElementsGuard()],
        pitch_postprocessors=build_pitch_postprocessors(),
        geometry_check=geometry_check,
        checkpoint_geometry_check=checkpoint_geometry_check,
        checkpoint_pitch_check=checkpoint_pitch_check,
        checkpoint_entities_check=checkpoint_entities_check,
    )
