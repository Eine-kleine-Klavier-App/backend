from dataclasses import dataclass

from piano_app.domain.score.document.models.context import DynamicChange
from piano_app.domain.score.document.models.notation import DynamicMarking
from piano_app.domain.score.document.models.structural import TemporalAnchor, Voice
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    CreateMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateDynamicChangeAction(CreateMutationAction[DynamicChange]):
    """Creates a dynamic change on its anchor."""

    start: TemporalAnchor
    voice: Voice
    dynamic: DynamicMarking
