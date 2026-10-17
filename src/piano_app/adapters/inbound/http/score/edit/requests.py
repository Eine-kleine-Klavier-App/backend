from typing import Self

from pydantic import BaseModel, Field, model_validator

from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    Fingering,
    RhythmicValue,
    StemDirection,
    StemOverride,
)
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation.compiler import (
    DeleteBatchIntent,
    InsertNoteIntent,
    ResetStemIntent,
    SetStemIntent,
    TieNotesIntent,
)


class PositionModel(BaseModel):
    numerator: int = Field(ge=0)
    denominator: int = Field(gt=0)

    def to_domain(self) -> MeasurePosition:
        return MeasurePosition.of(numerator=self.numerator, denominator=self.denominator)


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


class InsertNoteRequest(BaseModel):
    voice_id: str
    staff_id: str
    measure_id: str
    position: PositionModel
    written_value: RhythmicValueModel
    staff_step: int
    accidental: Accidental
    fingering: Fingering = Fingering.NONE

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
        )


class TieNotesRequest(BaseModel):
    start_note_id: str
    end_note_id: str

    def to_intent(self) -> TieNotesIntent:
        return TieNotesIntent(start_note_id=self.start_note_id, end_note_id=self.end_note_id)


class DeleteBatchRequest(BaseModel):
    entity_ids: list[str]

    def to_intent(self) -> DeleteBatchIntent:
        return DeleteBatchIntent(entity_ids=tuple(self.entity_ids))


class StemOverrideModel(BaseModel):
    direction: StemDirection
    length_percent: int = Field(default=100, gt=0)

    def to_domain(self) -> StemOverride:
        return StemOverride(direction=self.direction, length_percent=self.length_percent)


class SetStemsRequest(BaseModel):
    """Draw these carriers' stems as given; ``override: null`` draws them automatically."""

    carrier_ids: list[str]
    override: StemOverrideModel | None

    def to_intent(self) -> SetStemIntent | ResetStemIntent:
        if self.override is None:
            return ResetStemIntent(carrier_ids=tuple(self.carrier_ids))

        return SetStemIntent(
            carrier_ids=tuple(self.carrier_ids), override=self.override.to_domain()
        )
