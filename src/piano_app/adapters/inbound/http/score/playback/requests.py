from fractions import Fraction

from pydantic import BaseModel, Field


class GlobalPositionModel(BaseModel):
    numerator: int = Field(ge=0, strict=True)
    denominator: int = Field(gt=0, strict=True)

    def to_domain(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)


class PlaybackRequest(BaseModel):
    start: GlobalPositionModel = Field(description="Global musical coordinate in whole-note units.")


class PreviewRequest(BaseModel):
    carrier_id: str = Field(min_length=1)
    note_ids: list[str] | None = Field(default=None, min_length=1)
