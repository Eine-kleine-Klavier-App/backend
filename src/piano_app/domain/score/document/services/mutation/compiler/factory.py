from .compiler import MutationCompiler
from .context import (
    AddContextVoiceCompiler,
    AddRefrainEndingCompiler,
    AppendVoltaFragmentCompiler,
    CreateHairpinCompiler,
    CreateOctaveTranspositionCompiler,
    CreateRefrainCompiler,
    CreateSlurCompiler,
    CreateSustainHoldCompiler,
    CreateTempoTransitionCompiler,
    CreateVoltaCompiler,
    DeleteClefCompiler,
    DeleteOctaveTranspositionCompiler,
    MoveContextEndCompiler,
    MoveContextStartCompiler,
    MoveRefrainEndCompiler,
    MoveRefrainStartCompiler,
    MoveVoltaBoundaryCompiler,
    MoveVoltaStartCompiler,
    OpenContextEndCompiler,
    RemoveContextVoiceCompiler,
    SetClefCompiler,
    SetDynamicCompiler,
    SetHairpinTargetCompiler,
    SetKeySignatureCompiler,
    SetRefrainTimesCompiler,
    SetTempoCompiler,
    SetTempoTransitionTargetCompiler,
    SetVoltaFragmentPassesCompiler,
    SetVoltaTimesCompiler,
    SplitVoltaFragmentCompiler,
)
from .create import (
    AddGraceCarrierNoteCompiler,
    AddGraceNoteCompiler,
    AppendMeasureCompiler,
    ChangeGraceTypeCompiler,
    ChangeGraceValueCompiler,
    CreateBeamCompiler,
    CreateTupletWithNoteCompiler,
    CreateTupletWithRestCompiler,
    GlissandoNotesCompiler,
    InsertMeasureCompiler,
    InsertNoteCompiler,
    InsertRestCompiler,
    RemoveGraceNoteCompiler,
    TieNotesCompiler,
)
from .delete import DeleteBatchCompiler, RemoveMeasureCompiler
from .intents import (
    AddContextVoiceIntent,
    AddGraceCarrierNoteIntent,
    AddGraceNoteIntent,
    AddRefrainEndingIntent,
    AppendMeasureIntent,
    AppendVoltaFragmentIntent,
    ChangeDurationIntent,
    ChangeGraceTypeIntent,
    ChangeGraceValueIntent,
    ChangePitchIntent,
    ChangeTimeSignatureIntent,
    CreateBeamIntent,
    CreateHairpinIntent,
    CreateOctaveTranspositionIntent,
    CreateRefrainIntent,
    CreateSlurIntent,
    CreateSustainHoldIntent,
    CreateTempoTransitionIntent,
    CreateTupletWithNoteIntent,
    CreateTupletWithRestIntent,
    CreateVoltaIntent,
    DeleteBatchIntent,
    DeleteClefIntent,
    DeleteOctaveTranspositionIntent,
    GlissandoNotesIntent,
    InsertMeasureIntent,
    InsertNoteIntent,
    InsertRestIntent,
    MoveContextEndIntent,
    MoveContextStartIntent,
    MoveNoteToStaffIntent,
    MoveRefrainEndIntent,
    MoveRefrainStartIntent,
    MoveVoltaBoundaryIntent,
    MoveVoltaStartIntent,
    OpenContextEndIntent,
    RemoveContextVoiceIntent,
    RemoveGraceNoteIntent,
    RemoveMeasureIntent,
    SetAccidentalIntent,
    SetArticulationIntent,
    SetCarrierMarksIntent,
    SetClefIntent,
    SetDynamicIntent,
    SetFingeringIntent,
    SetHairpinTargetIntent,
    SetKeySignatureIntent,
    SetOrnamentIntent,
    SetRefrainTimesIntent,
    SetTempoIntent,
    SetTempoTransitionTargetIntent,
    SetVoltaFragmentPassesIntent,
    SetVoltaTimesIntent,
    ShiftStaffStepsIntent,
    SplitBeamIntent,
    SplitVoltaFragmentIntent,
    TieNotesIntent,
    ToggleArticulationIntent,
)
from .registry import IntentCompilerRegistry
from .update import (
    ChangeDurationCompiler,
    ChangePitchCompiler,
    ChangeTimeSignatureCompiler,
    MoveNoteToStaffCompiler,
    SetAccidentalCompiler,
    SetArticulationCompiler,
    SetCarrierMarksCompiler,
    SetFingeringCompiler,
    SetOrnamentCompiler,
    ShiftStaffStepsCompiler,
    SplitBeamCompiler,
    ToggleArticulationCompiler,
)


def _build_registry() -> IntentCompilerRegistry:
    registry: IntentCompilerRegistry = IntentCompilerRegistry()

    registry.register(intent_type=InsertNoteIntent, compiler=InsertNoteCompiler())
    registry.register(intent_type=AddGraceNoteIntent, compiler=AddGraceNoteCompiler())
    registry.register(intent_type=AddGraceCarrierNoteIntent, compiler=AddGraceCarrierNoteCompiler())
    registry.register(intent_type=RemoveGraceNoteIntent, compiler=RemoveGraceNoteCompiler())
    registry.register(intent_type=ChangeGraceTypeIntent, compiler=ChangeGraceTypeCompiler())
    registry.register(intent_type=ChangeGraceValueIntent, compiler=ChangeGraceValueCompiler())
    registry.register(intent_type=InsertRestIntent, compiler=InsertRestCompiler())
    registry.register(intent_type=TieNotesIntent, compiler=TieNotesCompiler())
    registry.register(intent_type=GlissandoNotesIntent, compiler=GlissandoNotesCompiler())
    registry.register(intent_type=CreateBeamIntent, compiler=CreateBeamCompiler())
    registry.register(intent_type=SplitBeamIntent, compiler=SplitBeamCompiler())
    registry.register(
        intent_type=CreateTupletWithNoteIntent,
        compiler=CreateTupletWithNoteCompiler(),
    )
    registry.register(
        intent_type=CreateTupletWithRestIntent,
        compiler=CreateTupletWithRestCompiler(),
    )
    registry.register(intent_type=DeleteBatchIntent, compiler=DeleteBatchCompiler())
    registry.register(intent_type=SetFingeringIntent, compiler=SetFingeringCompiler())
    registry.register(intent_type=SetArticulationIntent, compiler=SetArticulationCompiler())
    registry.register(intent_type=ToggleArticulationIntent, compiler=ToggleArticulationCompiler())
    registry.register(intent_type=SetOrnamentIntent, compiler=SetOrnamentCompiler())
    registry.register(intent_type=SetCarrierMarksIntent, compiler=SetCarrierMarksCompiler())
    registry.register(intent_type=ChangeDurationIntent, compiler=ChangeDurationCompiler())
    registry.register(intent_type=AppendMeasureIntent, compiler=AppendMeasureCompiler())
    registry.register(intent_type=InsertMeasureIntent, compiler=InsertMeasureCompiler())
    registry.register(intent_type=RemoveMeasureIntent, compiler=RemoveMeasureCompiler())
    registry.register(
        intent_type=ChangeTimeSignatureIntent,
        compiler=ChangeTimeSignatureCompiler(),
    )

    registry.register(intent_type=CreateHairpinIntent, compiler=CreateHairpinCompiler())
    registry.register(
        intent_type=CreateOctaveTranspositionIntent, compiler=CreateOctaveTranspositionCompiler()
    )
    registry.register(intent_type=CreateSlurIntent, compiler=CreateSlurCompiler())
    registry.register(intent_type=CreateSustainHoldIntent, compiler=CreateSustainHoldCompiler())
    registry.register(
        intent_type=CreateTempoTransitionIntent, compiler=CreateTempoTransitionCompiler()
    )
    registry.register(intent_type=MoveContextEndIntent, compiler=MoveContextEndCompiler())
    registry.register(intent_type=MoveContextStartIntent, compiler=MoveContextStartCompiler())
    registry.register(intent_type=OpenContextEndIntent, compiler=OpenContextEndCompiler())
    registry.register(intent_type=CreateRefrainIntent, compiler=CreateRefrainCompiler())
    registry.register(intent_type=SetRefrainTimesIntent, compiler=SetRefrainTimesCompiler())
    registry.register(intent_type=CreateVoltaIntent, compiler=CreateVoltaCompiler())
    registry.register(intent_type=MoveRefrainStartIntent, compiler=MoveRefrainStartCompiler())
    registry.register(intent_type=MoveRefrainEndIntent, compiler=MoveRefrainEndCompiler())
    registry.register(intent_type=MoveVoltaBoundaryIntent, compiler=MoveVoltaBoundaryCompiler())
    registry.register(intent_type=MoveVoltaStartIntent, compiler=MoveVoltaStartCompiler())
    registry.register(
        intent_type=SetVoltaFragmentPassesIntent, compiler=SetVoltaFragmentPassesCompiler()
    )
    registry.register(intent_type=SetVoltaTimesIntent, compiler=SetVoltaTimesCompiler())
    registry.register(intent_type=AppendVoltaFragmentIntent, compiler=AppendVoltaFragmentCompiler())
    registry.register(intent_type=SplitVoltaFragmentIntent, compiler=SplitVoltaFragmentCompiler())
    registry.register(intent_type=AddRefrainEndingIntent, compiler=AddRefrainEndingCompiler())
    registry.register(intent_type=SetDynamicIntent, compiler=SetDynamicCompiler())
    registry.register(intent_type=AddContextVoiceIntent, compiler=AddContextVoiceCompiler())
    registry.register(intent_type=RemoveContextVoiceIntent, compiler=RemoveContextVoiceCompiler())
    registry.register(intent_type=SetHairpinTargetIntent, compiler=SetHairpinTargetCompiler())
    registry.register(intent_type=SetKeySignatureIntent, compiler=SetKeySignatureCompiler())
    registry.register(intent_type=SetTempoIntent, compiler=SetTempoCompiler())
    registry.register(
        intent_type=SetTempoTransitionTargetIntent, compiler=SetTempoTransitionTargetCompiler()
    )
    registry.register(intent_type=SetClefIntent, compiler=SetClefCompiler())
    registry.register(intent_type=DeleteClefIntent, compiler=DeleteClefCompiler())
    registry.register(
        intent_type=DeleteOctaveTranspositionIntent, compiler=DeleteOctaveTranspositionCompiler()
    )
    registry.register(intent_type=ChangePitchIntent, compiler=ChangePitchCompiler())
    registry.register(intent_type=ShiftStaffStepsIntent, compiler=ShiftStaffStepsCompiler())
    registry.register(intent_type=SetAccidentalIntent, compiler=SetAccidentalCompiler())
    registry.register(intent_type=MoveNoteToStaffIntent, compiler=MoveNoteToStaffCompiler())

    return registry


def build_compiler() -> MutationCompiler:
    return MutationCompiler(registry=_build_registry())
