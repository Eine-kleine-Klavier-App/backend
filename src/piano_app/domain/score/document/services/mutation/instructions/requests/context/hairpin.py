from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.context import Hairpin
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition, Voice
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
    UpdateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateHairpinRequest(CreateMutationRequest[Hairpin]):
    """A request to assert a hairpin over a span for one voice: ``steps`` dynamic levels
    from the level in force at its start, above zero a crescendo, below a diminuendo."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS
    creates: ClassVar[type[ScoreEntity]] = Hairpin

    start_measure: Measure
    start_position: MeasurePosition
    end_measure: Measure
    end_position: MeasurePosition
    voice: Voice
    steps: int


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateHairpinStepsRequest(UpdateMutationRequest[Hairpin]):
    """A request to change by how many dynamic levels a hairpin moves, keeping the hairpin."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS

    steps: int
