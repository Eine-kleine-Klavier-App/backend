from dataclasses import dataclass

from piano_app.domain.score.document.models.context import Context, SpanContext
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    DeleteMutationAction,
    UpdateMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteContextAction(DeleteMutationAction[Context]):
    """Deletes a context."""


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateContextStartAction(UpdateMutationAction[Context]):
    """Moves a context's start to another anchor."""

    start: TemporalAnchor


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateContextEndAction(UpdateMutationAction[SpanContext]):
    """Moves a span context's end to another anchor, or to the end of the score (``None``)."""

    end: TemporalAnchor | None
