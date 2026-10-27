from dataclasses import dataclass
from fractions import Fraction
from typing import ClassVar

from piano_app.domain.score.document.models.context import SpanContext
from piano_app.domain.score.document.models.structural import Measure
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    MutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class KeepContextEndsRequest(MutationRequest):
    """A request to keep the end of each span context of ``contexts`` at ``offset`` from the
    start of ``measures`` — contiguous, in score order — moving it there when the barlines
    moved under it."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS

    contexts: tuple[SpanContext, ...]
    measures: tuple[Measure, ...]
    offset: Fraction
