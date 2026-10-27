from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.context import SustainHold
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateSustainHoldRequest(CreateMutationRequest[SustainHold]):
    """A request to assert the damper pedal held over a span of the whole score."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS
    creates: ClassVar[type[ScoreEntity]] = SustainHold

    start_measure: Measure
    start_position: MeasurePosition
    end_measure: Measure
    end_position: MeasurePosition
