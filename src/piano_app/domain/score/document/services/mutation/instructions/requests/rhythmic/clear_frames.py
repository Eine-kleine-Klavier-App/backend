from dataclasses import dataclass
from fractions import Fraction
from typing import ClassVar

from piano_app.domain.score.document.models.structural import Measure, MeasurePosition, Voice
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    MutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ClearFramesRequest(MutationRequest):
    """A request to remove the groups a new item of ``written_length`` would meet in its
    scope, before the item's spans are placed. ``written_length`` is read in the units of
    the scope holding the start."""

    axis: ClassVar[Axis | None] = Axis.FRAMES

    voice: Voice
    measure: Measure
    position: MeasurePosition
    written_length: Fraction
