from dataclasses import dataclass

from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import GlissandoType
from piano_app.domain.score.document.models.relations import Glissando
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    CreateMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateGlissandoAction(CreateMutationAction[Glissando]):
    """Creates a glissando between two notes."""

    start_note: Note
    end_note: Note
    glissando_type: GlissandoType
