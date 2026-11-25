from fractions import Fraction
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from piano_app.domain.score.document.models.notation import (
    Accidental,
    Articulation,
    Clef,
    DottedRhythmicValue,
    DynamicMarking,
    Fingering,
    GlissandoType,
    GracePlacement,
    GraceType,
    Ornament,
    RhythmicSize,
    RhythmicValue,
    StemDirection,
    TempoMarking,
)
from piano_app.domain.score.document.models.presentation import (
    EndpointOffsets,
    HorizontalEndpointOffsets,
    HorizontalOffset,
    PresentationTarget,
    ReferencePoint,
    VerticalOffset,
)
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation.compiler import (
    AddGraceCarrierNoteIntent,
    AddGraceNoteIntent,
    AddRefrainEndingIntent,
    AppendMeasureIntent,
    AppendVoltaFragmentIntent,
    CarrierMarks,
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
    PitchEditMode,
    RemoveGraceNoteIntent,
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
    VoltaFragmentIntent,
)
from piano_app.domain.score.document.services.mutation.compiler.intents.create import (
    DEFAULT_BEAM_SHARE,
)
from piano_app.domain.score.document.services.presentation import (
    PresentationCommand,
    SetDirection,
    SetEndpointOffsets,
    SetHorizontalEndpointOffsets,
    SetHorizontalOffset,
    SetVerticalOffset,
)


class PositionModel(BaseModel):
    numerator: int = Field(ge=0)
    denominator: int = Field(gt=0)

    def to_domain(self) -> MeasurePosition:
        return MeasurePosition.of(numerator=self.numerator, denominator=self.denominator)


class FractionModel(BaseModel):
    """A part of a whole: from nothing up to the whole."""

    numerator: int = Field(ge=0)
    denominator: int = Field(gt=0)

    @model_validator(mode="after")
    def _check_proper(self) -> Self:
        if self.numerator > self.denominator:
            raise ValueError("A part of a whole cannot exceed the whole.")
        return self

    @classmethod
    def of(cls, fraction: Fraction) -> Self:
        return cls(numerator=fraction.numerator, denominator=fraction.denominator)

    def to_domain(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)


class RhythmicValueModel(BaseModel):
    value: RhythmicValue
    dots: int = Field(default=0, ge=0)

    # dots reaching below the smallest note are rejected by the value object itself;
    # building it here turns that into a 422 instead of an error past validation
    @model_validator(mode="after")
    def _check_representable(self) -> Self:
        self.to_domain()
        return self

    def to_domain(self) -> DottedRhythmicValue:
        return DottedRhythmicValue(value=self.value, dots_count=self.dots)


class RhythmicSizeModel(BaseModel):
    value: RhythmicValueModel
    count: int = Field(ge=1)

    def to_domain(self) -> RhythmicSize:
        return RhythmicSize(value=self.value.to_domain(), count=self.count)


class AddGraceNoteRequest(BaseModel):
    host_carrier_id: str
    placement: GracePlacement
    grace_type: GraceType
    written_value: RhythmicValueModel
    staff_id: str
    staff_step: int
    accidental: Accidental | None = None
    fingering: Fingering = Fingering.NONE
    after_carrier_id: str | None = None

    def to_intent(self) -> AddGraceNoteIntent:
        return AddGraceNoteIntent(
            host_carrier_id=self.host_carrier_id,
            placement=self.placement,
            grace_type=self.grace_type,
            written_value=self.written_value.to_domain(),
            staff_id=self.staff_id,
            staff_step=self.staff_step,
            accidental=self.accidental,
            fingering=self.fingering,
            after_carrier_id=self.after_carrier_id,
        )


class AddGraceCarrierNoteRequest(BaseModel):
    carrier_id: str
    staff_id: str
    staff_step: int
    accidental: Accidental | None = None
    fingering: Fingering = Fingering.NONE

    def to_intent(self) -> AddGraceCarrierNoteIntent:
        return AddGraceCarrierNoteIntent(
            carrier_id=self.carrier_id,
            staff_id=self.staff_id,
            staff_step=self.staff_step,
            accidental=self.accidental,
            fingering=self.fingering,
        )


class ChangeGraceValueRequest(BaseModel):
    carrier_id: str
    written_value: RhythmicValueModel

    def to_intent(self) -> ChangeGraceValueIntent:
        return ChangeGraceValueIntent(
            carrier_id=self.carrier_id, written_value=self.written_value.to_domain()
        )


class ChangeGraceTypeRequest(BaseModel):
    note_id: str
    grace_type: GraceType

    def to_intent(self) -> ChangeGraceTypeIntent:
        return ChangeGraceTypeIntent(note_id=self.note_id, grace_type=self.grace_type)


class RemoveGraceNoteRequest(BaseModel):
    note_id: str

    def to_intent(self) -> RemoveGraceNoteIntent:
        return RemoveGraceNoteIntent(note_id=self.note_id)


class InsertNoteRequest(BaseModel):
    voice_id: str
    staff_id: str
    measure_id: str
    position: PositionModel
    written_value: RhythmicValueModel
    staff_step: int
    accidental: Accidental | None = None
    fingering: Fingering = Fingering.NONE
    beam_share: FractionModel = Field(default_factory=lambda: FractionModel.of(DEFAULT_BEAM_SHARE))

    def to_intent(self) -> InsertNoteIntent:
        return InsertNoteIntent(
            voice_id=self.voice_id,
            staff_id=self.staff_id,
            measure_id=self.measure_id,
            position=self.position.to_domain(),
            written_value=self.written_value.to_domain(),
            staff_step=self.staff_step,
            accidental=self.accidental,
            fingering=self.fingering,
            beam_share=self.beam_share.to_domain(),
        )


class InsertRestRequest(BaseModel):
    voice_id: str
    staff_id: str
    measure_id: str
    position: PositionModel
    written_value: RhythmicValueModel

    def to_intent(self) -> InsertRestIntent:
        return InsertRestIntent(
            voice_id=self.voice_id,
            staff_id=self.staff_id,
            measure_id=self.measure_id,
            position=self.position.to_domain(),
            written_value=self.written_value.to_domain(),
        )


class TupletNoteModel(BaseModel):
    staff_step: int
    accidental: Accidental | None = None
    fingering: Fingering = Fingering.NONE


class CreateTupletRequest(BaseModel):
    """Create a tuplet with its first element: the note given, or a rest when ``note`` is
    ``null``."""

    voice_id: str
    staff_id: str
    measure_id: str
    position: PositionModel
    written_size: RhythmicSizeModel
    occupied_size: RhythmicSizeModel
    written_value: RhythmicValueModel
    note: TupletNoteModel | None

    def to_intent(self) -> CreateTupletWithNoteIntent | CreateTupletWithRestIntent:
        if self.note is None:
            return CreateTupletWithRestIntent(
                voice_id=self.voice_id,
                staff_id=self.staff_id,
                measure_id=self.measure_id,
                position=self.position.to_domain(),
                written_size=self.written_size.to_domain(),
                occupied_size=self.occupied_size.to_domain(),
                written_value=self.written_value.to_domain(),
            )

        return CreateTupletWithNoteIntent(
            voice_id=self.voice_id,
            staff_id=self.staff_id,
            measure_id=self.measure_id,
            position=self.position.to_domain(),
            written_size=self.written_size.to_domain(),
            occupied_size=self.occupied_size.to_domain(),
            written_value=self.written_value.to_domain(),
            staff_step=self.note.staff_step,
            accidental=self.note.accidental,
            fingering=self.note.fingering,
        )


class TieNotesRequest(BaseModel):
    start_note_id: str
    end_note_id: str

    def to_intent(self) -> TieNotesIntent:
        return TieNotesIntent(start_note_id=self.start_note_id, end_note_id=self.end_note_id)


class GlissandoNotesRequest(BaseModel):
    start_note_id: str
    end_note_id: str
    glissando_type: GlissandoType = GlissandoType.STRAIGHT

    def to_intent(self) -> GlissandoNotesIntent:
        return GlissandoNotesIntent(
            start_note_id=self.start_note_id,
            end_note_id=self.end_note_id,
            glissando_type=self.glissando_type,
        )


class CreateBeamRequest(BaseModel):
    carrier_ids: list[str]

    def to_intent(self) -> CreateBeamIntent:
        return CreateBeamIntent(carrier_ids=tuple(self.carrier_ids))


class SplitBeamRequest(BaseModel):
    beam_id: str
    before_carrier_id: str

    def to_intent(self) -> SplitBeamIntent:
        return SplitBeamIntent(beam_id=self.beam_id, before_carrier_id=self.before_carrier_id)


class DeleteBatchRequest(BaseModel):
    entity_ids: list[str]

    def to_intent(self) -> DeleteBatchIntent:
        return DeleteBatchIntent(entity_ids=tuple(self.entity_ids))


class SetFingeringRequest(BaseModel):
    note_id: str
    fingering: Fingering

    def to_intent(self) -> SetFingeringIntent:
        return SetFingeringIntent(note_id=self.note_id, fingering=self.fingering)


class SetArticulationRequest(BaseModel):
    carrier_id: str
    articulations: list[Articulation]

    def to_intent(self) -> SetArticulationIntent:
        return SetArticulationIntent(
            carrier_id=self.carrier_id,
            articulations=frozenset(self.articulations),
        )


class ToggleArticulationRequest(BaseModel):
    carrier_id: str
    articulation: Articulation

    def to_intent(self) -> ToggleArticulationIntent:
        return ToggleArticulationIntent(
            carrier_id=self.carrier_id,
            articulation=self.articulation,
        )


class SetOrnamentRequest(BaseModel):
    carrier_id: str
    ornament: Ornament

    def to_intent(self) -> SetOrnamentIntent:
        return SetOrnamentIntent(carrier_id=self.carrier_id, ornament=self.ornament)


class CarrierMarksItem(BaseModel):
    carrier_id: str
    articulations: list[Articulation] | None = None
    ornament: Ornament | None = None


class SetCarrierMarksRequest(BaseModel):
    """Marks for several carriers in one gesture; a mark left out is not touched."""

    items: list[CarrierMarksItem] = Field(min_length=1)

    def to_intent(self) -> SetCarrierMarksIntent:
        return SetCarrierMarksIntent(
            items=tuple(
                CarrierMarks(
                    carrier_id=item.carrier_id,
                    articulations=None
                    if item.articulations is None
                    else frozenset(item.articulations),
                    ornament=item.ornament,
                )
                for item in self.items
            )
        )


class ChangeDurationRequest(BaseModel):
    carrier_id: str
    written_value: RhythmicValueModel

    def to_intent(self) -> ChangeDurationIntent:
        return ChangeDurationIntent(
            carrier_id=self.carrier_id,
            written_value=self.written_value.to_domain(),
        )


class InsertMeasureRequest(BaseModel):
    """Insert a measure before ``before_measure_id``; without it the measure is appended
    after the last one."""

    before_measure_id: str | None = None

    def to_intent(self) -> AppendMeasureIntent | InsertMeasureIntent:
        if self.before_measure_id is None:
            return AppendMeasureIntent()

        return InsertMeasureIntent(before_measure_id=self.before_measure_id)


class ChangeTimeSignatureRequest(BaseModel):
    measure_ids: list[str]
    time_signature: RhythmicSizeModel

    def to_intent(self) -> ChangeTimeSignatureIntent:
        return ChangeTimeSignatureIntent(
            measure_ids=tuple(self.measure_ids),
            time_signature=self.time_signature.to_domain(),
        )


class SetTempoRequest(BaseModel):
    """Set the tempo from this place on: a number with its beat, a word, or both. A word alone
    takes the middle of its usual range, in quarter notes."""

    measure_id: str
    position: PositionModel
    beat: RhythmicValueModel | None = None
    bpm: int | None = Field(default=None, ge=1)
    show_label: bool = False
    label: TempoMarking | None = None

    def to_intent(self) -> SetTempoIntent:
        return SetTempoIntent(
            measure_id=self.measure_id,
            position=self.position.to_domain(),
            beat=None if self.beat is None else self.beat.to_domain(),
            bpm=self.bpm,
            show_label=self.show_label,
            label=self.label,
        )


class CreateTempoTransitionRequest(BaseModel):
    """Speed up or slow down between two places, to a number of beats per minute of the
    beat of the tempo in force at the start."""

    start_measure_id: str
    start_position: PositionModel
    end_measure_id: str
    end_position: PositionModel
    target_bpm: int = Field(ge=1)

    def to_intent(self) -> CreateTempoTransitionIntent:
        return CreateTempoTransitionIntent(
            start_measure_id=self.start_measure_id,
            start_position=self.start_position.to_domain(),
            end_measure_id=self.end_measure_id,
            end_position=self.end_position.to_domain(),
            target_bpm=self.target_bpm,
        )


class SetTempoTransitionTargetRequest(BaseModel):
    transition_id: str
    target_bpm: int = Field(ge=1)

    def to_intent(self) -> SetTempoTransitionTargetIntent:
        return SetTempoTransitionTargetIntent(
            transition_id=self.transition_id, target_bpm=self.target_bpm
        )


class SetDynamicRequest(BaseModel):
    measure_id: str
    position: PositionModel
    voice_ids: list[str] = Field(min_length=1)
    dynamic: DynamicMarking

    def to_intent(self) -> SetDynamicIntent:
        return SetDynamicIntent(
            measure_id=self.measure_id,
            position=self.position.to_domain(),
            voice_ids=tuple(self.voice_ids),
            dynamic=self.dynamic,
        )


class CreateHairpinRequest(BaseModel):
    """Grow or fade between two places, to a dynamic, for some voices: a hairpin for each."""

    start_measure_id: str
    start_position: PositionModel
    end_measure_id: str
    end_position: PositionModel
    voice_ids: list[str] = Field(min_length=1)
    target: DynamicMarking

    def to_intent(self) -> CreateHairpinIntent:
        return CreateHairpinIntent(
            start_measure_id=self.start_measure_id,
            start_position=self.start_position.to_domain(),
            end_measure_id=self.end_measure_id,
            end_position=self.end_position.to_domain(),
            voice_ids=tuple(self.voice_ids),
            target=self.target,
        )


class SetHairpinTargetRequest(BaseModel):
    hairpin_ids: list[str] = Field(min_length=1)
    target: DynamicMarking

    def to_intent(self) -> SetHairpinTargetIntent:
        return SetHairpinTargetIntent(hairpin_ids=tuple(self.hairpin_ids), target=self.target)


class SetKeySignatureRequest(BaseModel):
    """The accidental of each of the seven diatonic steps, C to B."""

    staff_id: str
    measure_id: str
    position: PositionModel
    alterations: list[Accidental] = Field(min_length=7, max_length=7)

    def to_intent(self) -> SetKeySignatureIntent:
        return SetKeySignatureIntent(
            staff_id=self.staff_id,
            measure_id=self.measure_id,
            position=self.position.to_domain(),
            alterations=tuple(self.alterations),
        )


class CreateSustainHoldRequest(BaseModel):
    start_measure_id: str
    start_position: PositionModel
    end_measure_id: str
    end_position: PositionModel

    def to_intent(self) -> CreateSustainHoldIntent:
        return CreateSustainHoldIntent(
            start_measure_id=self.start_measure_id,
            start_position=self.start_position.to_domain(),
            end_measure_id=self.end_measure_id,
            end_position=self.end_position.to_domain(),
        )


class CreateRefrainRequest(BaseModel):
    """A stretch of the whole score played several times; without an end it lasts until the
    end of the score."""

    start_measure_id: str
    start_position: PositionModel
    end_measure_id: str | None = None
    end_position: PositionModel | None = None
    times: int = Field(ge=2)

    def to_intent(self) -> CreateRefrainIntent:
        return CreateRefrainIntent(
            start_measure_id=self.start_measure_id,
            start_position=self.start_position.to_domain(),
            end_measure_id=self.end_measure_id,
            end_position=None if self.end_position is None else self.end_position.to_domain(),
            times=self.times,
        )


class AddRefrainEndingRequest(BaseModel):
    """The first ending of a repeat: the repeat becomes a volta, and the ending ends at the given
    place; without one it lasts until the end of the score."""

    refrain_id: str
    end_measure_id: str | None = None
    end_position: PositionModel | None = None

    def to_intent(self) -> AddRefrainEndingIntent:
        return AddRefrainEndingIntent(
            refrain_id=self.refrain_id,
            measure_id=self.end_measure_id,
            position=None if self.end_position is None else self.end_position.to_domain(),
        )


class SetRefrainTimesRequest(BaseModel):
    refrain_id: str
    times: int = Field(ge=2)

    def to_intent(self) -> SetRefrainTimesIntent:
        return SetRefrainTimesIntent(refrain_id=self.refrain_id, times=self.times)


class MoveRefrainStartRequest(BaseModel):
    refrain_id: str
    measure_id: str
    position: PositionModel

    def to_intent(self) -> MoveRefrainStartIntent:
        return MoveRefrainStartIntent(
            refrain_id=self.refrain_id,
            measure_id=self.measure_id,
            position=self.position.to_domain(),
        )


class MoveRefrainEndRequest(BaseModel):
    """Without a place the refrain lasts until the end of the score."""

    refrain_id: str
    measure_id: str | None = None
    position: PositionModel | None = None

    def to_intent(self) -> MoveRefrainEndIntent:
        return MoveRefrainEndIntent(
            refrain_id=self.refrain_id,
            measure_id=self.measure_id,
            position=None if self.position is None else self.position.to_domain(),
        )


class VoltaFragmentModel(BaseModel):
    """One fragment of a volta: where it ends (no end: the end of the score) and its passes."""

    end_measure_id: str | None = None
    end_position: PositionModel | None = None
    passes: list[int] = Field(min_length=1)

    def to_intent(self) -> VoltaFragmentIntent:
        return VoltaFragmentIntent(
            end_measure_id=self.end_measure_id,
            end_position=None if self.end_position is None else self.end_position.to_domain(),
            passes=tuple(self.passes),
        )


class CreateVoltaRequest(BaseModel):
    """The endings of a repeat: a body from where it starts to where it ends, and the
    fragments that follow it, each in its own passes."""

    start_measure_id: str
    start_position: PositionModel
    body_end_measure_id: str
    body_end_position: PositionModel
    fragments: list[VoltaFragmentModel] = Field(min_length=1)

    def to_intent(self) -> CreateVoltaIntent:
        return CreateVoltaIntent(
            start_measure_id=self.start_measure_id,
            start_position=self.start_position.to_domain(),
            body_end_measure_id=self.body_end_measure_id,
            body_end_position=self.body_end_position.to_domain(),
            fragments=tuple(fragment.to_intent() for fragment in self.fragments),
        )


class MoveVoltaBoundaryRequest(BaseModel):
    """Drag a boundary of a volta: 0 is where the body ends, ``i`` where fragment ``i`` ends.
    Without a place it is the end of the score."""

    volta_id: str
    boundary: int = Field(ge=0)
    measure_id: str | None = None
    position: PositionModel | None = None

    def to_intent(self) -> MoveVoltaBoundaryIntent:
        return MoveVoltaBoundaryIntent(
            volta_id=self.volta_id,
            boundary=self.boundary,
            measure_id=self.measure_id,
            position=None if self.position is None else self.position.to_domain(),
        )


class MoveVoltaStartRequest(BaseModel):
    volta_id: str
    measure_id: str
    position: PositionModel

    def to_intent(self) -> MoveVoltaStartIntent:
        return MoveVoltaStartIntent(
            volta_id=self.volta_id,
            measure_id=self.measure_id,
            position=self.position.to_domain(),
        )


class SetVoltaFragmentPassesRequest(BaseModel):
    """The passes of a fragment counted from zero; the first fragment is played in the passes
    the others leave."""

    volta_id: str
    fragment: int = Field(ge=0)
    passes: list[int] = Field(min_length=1)

    def to_intent(self) -> SetVoltaFragmentPassesIntent:
        return SetVoltaFragmentPassesIntent(
            volta_id=self.volta_id, fragment=self.fragment, passes=tuple(self.passes)
        )


class SetVoltaTimesRequest(BaseModel):
    """How many times a volta is played, two at least."""

    volta_id: str
    times: int = Field(ge=2)

    def to_intent(self) -> SetVoltaTimesIntent:
        return SetVoltaTimesIntent(volta_id=self.volta_id, times=self.times)


class AppendVoltaFragmentRequest(BaseModel):
    """A fragment after the last one; without a place it lasts until the end of the score."""

    volta_id: str
    measure_id: str | None = None
    position: PositionModel | None = None

    def to_intent(self) -> AppendVoltaFragmentIntent:
        return AppendVoltaFragmentIntent(
            volta_id=self.volta_id,
            measure_id=self.measure_id,
            position=None if self.position is None else self.position.to_domain(),
        )


class SplitVoltaFragmentRequest(BaseModel):
    volta_id: str
    measure_id: str
    position: PositionModel

    def to_intent(self) -> SplitVoltaFragmentIntent:
        return SplitVoltaFragmentIntent(
            volta_id=self.volta_id,
            measure_id=self.measure_id,
            position=self.position.to_domain(),
        )


class OpenContextEndRequest(BaseModel):
    """Make spans last until the end of the score."""

    context_ids: list[str] = Field(min_length=1)
    mode: PitchEditMode

    def to_intent(self) -> OpenContextEndIntent:
        return OpenContextEndIntent(context_ids=tuple(self.context_ids), mode=self.mode)


class CreateSlurRequest(BaseModel):
    start_measure_id: str
    start_position: PositionModel
    end_measure_id: str
    end_position: PositionModel
    voice_ids: list[str] = Field(min_length=1)

    def to_intent(self) -> CreateSlurIntent:
        return CreateSlurIntent(
            start_measure_id=self.start_measure_id,
            start_position=self.start_position.to_domain(),
            end_measure_id=self.end_measure_id,
            end_position=self.end_position.to_domain(),
            voice_ids=tuple(self.voice_ids),
        )


class SetClefRequest(BaseModel):
    """Set the clef from this place on; ``mode`` says whether the notes it reaches move to sound
    as before or stay on their steps and sound different."""

    staff_id: str
    measure_id: str
    position: PositionModel
    clef: Clef
    octave_transposition: int = 0
    mode: PitchEditMode

    def to_intent(self) -> SetClefIntent:
        return SetClefIntent(
            staff_id=self.staff_id,
            measure_id=self.measure_id,
            position=self.position.to_domain(),
            clef=self.clef,
            octave_transposition=self.octave_transposition,
            mode=self.mode,
        )


class DeleteClefRequest(BaseModel):
    """Take a clef out of the measures given (those only when none are given, the measure it
    stands in): the clef before it governs them and it returns at the start of the next measure.
    ``mode`` says whether the notes it reached move to sound as before or stay put."""

    clef_id: str
    measure_ids: list[str] = Field(default_factory=list)
    mode: PitchEditMode

    def to_intent(self) -> DeleteClefIntent:
        return DeleteClefIntent(
            clef_id=self.clef_id, measure_ids=tuple(self.measure_ids), mode=self.mode
        )


class DeleteOctaveTranspositionRequest(BaseModel):
    octave_id: str
    mode: PitchEditMode

    def to_intent(self) -> DeleteOctaveTranspositionIntent:
        return DeleteOctaveTranspositionIntent(octave_id=self.octave_id, mode=self.mode)


class CreateOctaveTranspositionRequest(BaseModel):
    staff_id: str
    start_measure_id: str
    start_position: PositionModel
    end_measure_id: str
    end_position: PositionModel
    octaves: int
    mode: PitchEditMode

    def to_intent(self) -> CreateOctaveTranspositionIntent:
        return CreateOctaveTranspositionIntent(
            staff_id=self.staff_id,
            start_measure_id=self.start_measure_id,
            start_position=self.start_position.to_domain(),
            end_measure_id=self.end_measure_id,
            end_position=self.end_position.to_domain(),
            octaves=self.octaves,
            mode=self.mode,
        )


class ChangePitchRequest(BaseModel):
    """Put a note on another step of its staff; the accidental stays and tied notes follow."""

    note_id: str
    staff_step: int

    def to_intent(self) -> ChangePitchIntent:
        return ChangePitchIntent(note_id=self.note_id, staff_step=self.staff_step)


class SetAccidentalRequest(BaseModel):
    """Give a note another accidental; it stays on its step and tied notes follow."""

    note_id: str
    accidental: Accidental

    def to_intent(self) -> SetAccidentalIntent:
        return SetAccidentalIntent(note_id=self.note_id, accidental=self.accidental)


class MoveNoteToStaffRequest(BaseModel):
    """Move a note to another staff; ``mode`` says whether it sounds as before or keeps its step."""

    note_id: str
    staff_id: str
    mode: PitchEditMode

    def to_intent(self) -> MoveNoteToStaffIntent:
        return MoveNoteToStaffIntent(note_id=self.note_id, staff_id=self.staff_id, mode=self.mode)


class ShiftStaffStepsRequest(BaseModel):
    note_ids: list[str] = Field(min_length=1)
    delta: int = Field(strict=True, ge=-1, le=1)

    def to_intent(self) -> ShiftStaffStepsIntent:
        return ShiftStaffStepsIntent(note_ids=tuple(self.note_ids), delta=self.delta)


class BeamOverrideModel(BaseModel):
    model_config = {"extra": "forbid", "allow_inf_nan": False}
    left_offset: float
    right_offset: float


class PresentationTargetModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: str = Field(min_length=1)
    reference: ReferencePoint = ReferencePoint.BODY

    def to_domain(self) -> PresentationTarget:
        return PresentationTarget(entity_id=self.entity_id, reference=self.reference)


class VerticalPlacementModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["vertical"]
    target: PresentationTargetModel
    offset: float | None = Field(allow_inf_nan=False)

    def to_domain(self) -> SetVerticalOffset:
        return SetVerticalOffset(
            target=self.target.to_domain(),
            value=None if self.offset is None else VerticalOffset(value=self.offset),
        )


class EndpointOffsetsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left: float = Field(allow_inf_nan=False)
    right: float = Field(allow_inf_nan=False)


class EndpointPlacementModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["endpoints"]
    target: PresentationTargetModel
    offsets: EndpointOffsetsModel | None

    def to_domain(self) -> SetEndpointOffsets:
        return SetEndpointOffsets(
            target=self.target.to_domain(),
            value=None
            if self.offsets is None
            else EndpointOffsets(left=self.offsets.left, right=self.offsets.right),
        )


class HorizontalPlacementModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["horizontal"]
    target: PresentationTargetModel
    offset: float | None = Field(allow_inf_nan=False)

    def to_domain(self) -> SetHorizontalOffset:
        return SetHorizontalOffset(
            target=self.target.to_domain(),
            value=None if self.offset is None else HorizontalOffset(value=self.offset),
        )


class HorizontalEndpointOffsetsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left: float = Field(allow_inf_nan=False)
    right: float = Field(allow_inf_nan=False)


class HorizontalEndpointPlacementModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["horizontal_endpoints"]
    target: PresentationTargetModel
    offsets: HorizontalEndpointOffsetsModel | None

    def to_domain(self) -> SetHorizontalEndpointOffsets:
        return SetHorizontalEndpointOffsets(
            target=self.target.to_domain(),
            value=None
            if self.offsets is None
            else HorizontalEndpointOffsets(left=self.offsets.left, right=self.offsets.right),
        )


class DirectedPlacementModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["direction"]
    target: PresentationTargetModel
    direction: StemDirection | None

    def to_domain(self) -> SetDirection:
        return SetDirection(target=self.target.to_domain(), value=self.direction)


type PresentationChangeModel = Annotated[
    VerticalPlacementModel
    | EndpointPlacementModel
    | DirectedPlacementModel
    | HorizontalPlacementModel
    | HorizontalEndpointPlacementModel,
    Field(discriminator="kind"),
]


class EditPresentationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    changes: list[PresentationChangeModel] = Field(min_length=1)

    def to_commands(self) -> list[PresentationCommand]:
        return [change.to_domain() for change in self.changes]


class MoveContextStartRequest(BaseModel):
    """The new start of contexts; ``presentation`` changes are part of the same gesture."""

    context_ids: list[str] = Field(min_length=1)
    measure_id: str
    position: PositionModel
    mode: PitchEditMode
    presentation: list[PresentationChangeModel] = Field(default_factory=list)

    def to_intent(self) -> MoveContextStartIntent:
        return MoveContextStartIntent(
            context_ids=tuple(self.context_ids),
            measure_id=self.measure_id,
            position=self.position.to_domain(),
            mode=self.mode,
        )

    def to_presentation(self) -> list[PresentationCommand]:
        return [change.to_domain() for change in self.presentation]


class MoveContextEndRequest(BaseModel):
    """The new end of spans; ``presentation`` changes are part of the same gesture."""

    context_ids: list[str] = Field(min_length=1)
    measure_id: str
    position: PositionModel
    mode: PitchEditMode
    presentation: list[PresentationChangeModel] = Field(default_factory=list)

    def to_intent(self) -> MoveContextEndIntent:
        return MoveContextEndIntent(
            context_ids=tuple(self.context_ids),
            measure_id=self.measure_id,
            position=self.position.to_domain(),
            mode=self.mode,
        )

    def to_presentation(self) -> list[PresentationCommand]:
        return [change.to_domain() for change in self.presentation]
