from dataclasses import dataclass

from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateRefrainIntent(EditIntent):
    """Play a stretch of the whole score several times; without an end it lasts until the end
    of the score."""

    start_measure_id: str
    start_position: MeasurePosition
    end_measure_id: str | None
    end_position: MeasurePosition | None
    times: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SetRefrainTimesIntent(EditIntent):
    """Change how many times a refrain is played."""

    refrain_id: str
    times: int


@dataclass(frozen=True, slots=True, kw_only=True)
class MoveRefrainStartIntent(EditIntent):
    """Move the place a refrain starts at."""

    refrain_id: str
    measure_id: str
    position: MeasurePosition


@dataclass(frozen=True, slots=True, kw_only=True)
class MoveRefrainEndIntent(EditIntent):
    """Move the place a refrain ends at; without a place it lasts until the end of the score."""

    refrain_id: str
    measure_id: str | None
    position: MeasurePosition | None
