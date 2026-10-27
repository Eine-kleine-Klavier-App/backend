from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.context import Refrain
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
    UpdateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateRefrainRequest(CreateMutationRequest[Refrain]):
    """A request to assert a stretch of the whole score played ``times`` times; without an end
    measure it lasts until the end of the score."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS
    creates: ClassVar[type[ScoreEntity]] = Refrain

    start_measure: Measure
    start_position: MeasurePosition
    end_measure: Measure | None
    end_position: MeasurePosition | None
    times: int


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateRefrainTimesRequest(UpdateMutationRequest[Refrain]):
    """A request to change how many times a refrain is played, keeping it."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS

    times: int


@dataclass(frozen=True, slots=True, kw_only=True)
class MoveRefrainStartRequest(UpdateMutationRequest[Refrain]):
    """A request to move the place a refrain starts at, keeping it."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS

    measure: Measure
    position: MeasurePosition


@dataclass(frozen=True, slots=True, kw_only=True)
class MoveRefrainEndRequest(UpdateMutationRequest[Refrain]):
    """A request to move the place a refrain ends at, keeping it; no measure means the end of
    the score."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS

    measure: Measure | None
    position: MeasurePosition | None


@dataclass(frozen=True, slots=True, kw_only=True)
class CollapseRefrainRequest(UpdateMutationRequest[Refrain]):
    """A request to draw the ends of a refrain that lie in a measure about to be removed to
    where the measure ends; a refrain left with no length is deleted."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS

    measure: Measure
