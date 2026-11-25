from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import Context, SpanContext
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    MutationRequest,
    UpdateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateContextStartRequest(UpdateMutationRequest[Context]):
    """A request to move a context's start to ``position`` in ``measure``, keeping the
    context; a span context's start must stay before its end."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS

    measure: Measure
    position: MeasurePosition


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateContextEndRequest(UpdateMutationRequest[SpanContext]):
    """A request to move a span context's end to ``position`` in ``measure``, keeping the
    context; its end must stay after its start."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS

    measure: Measure
    position: MeasurePosition


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenContextEndRequest(UpdateMutationRequest[SpanContext]):
    """A request to make a span context last until the end of the score, keeping the context."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS


@dataclass(frozen=True, slots=True, kw_only=True)
class CloseOpenContextEndsRequest(MutationRequest):
    """A request, made right after a measure is added after the last one, to anchor the end of
    every span that lasted until the end of the score at the start of that measure: such a span
    stays where it was instead of growing to cover the new measure."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS

    document: ScoreDocument
