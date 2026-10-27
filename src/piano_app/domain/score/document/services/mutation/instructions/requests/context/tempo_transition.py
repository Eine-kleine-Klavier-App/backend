from dataclasses import dataclass
from fractions import Fraction
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.context import TempoTransition
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
    UpdateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateTempoTransitionRequest(CreateMutationRequest[TempoTransition]):
    """A request to assert a gradual tempo change over a span: ``ratio`` is the ratio of
    speed at its end to the speed in force at its start — above one an accelerando, below a
    ritardando."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS
    creates: ClassVar[type[ScoreEntity]] = TempoTransition

    start_measure: Measure
    start_position: MeasurePosition
    end_measure: Measure
    end_position: MeasurePosition
    ratio: Fraction


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateTempoTransitionRatioRequest(UpdateMutationRequest[TempoTransition]):
    """A request to change the ratio of speed a tempo transition ends at, keeping it."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS

    ratio: Fraction
