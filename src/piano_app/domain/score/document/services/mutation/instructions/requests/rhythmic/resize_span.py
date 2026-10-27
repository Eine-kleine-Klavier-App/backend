from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models.notation import DottedRhythmicValue
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    MutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ResizeSpanRequest(MutationRequest):
    """A request to give an existing leaf the span of ``written_value``, from where it
    starts: where its new span lies, and what happens to the spans it meets.
    ``written_value`` is read in the units of the leaf's scope."""

    axis: ClassVar[Axis | None] = Axis.FRAMES

    leaf: LeafRhythmicContainer
    written_value: DottedRhythmicValue
