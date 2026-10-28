from dataclasses import dataclass

from piano_app.domain.score.document.models.context import Slur
from piano_app.domain.score.document.models.structural import TemporalAnchor, Voice
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    CreateMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateSlurAction(CreateMutationAction[Slur]):
    """Creates a slur on its anchors."""

    start: TemporalAnchor
    end: TemporalAnchor
    voices: tuple[Voice, ...]
