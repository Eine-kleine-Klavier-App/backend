from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import GlissandoType
from piano_app.domain.score.document.models.relations import Glissando
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
    MutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CheckGlissandoRequest(MutationRequest):
    """A request to remove ``glissando`` when its notes are no longer neighbours."""

    axis: ClassVar[Axis | None] = Axis.RELATIONS

    glissando: Glissando


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateGlissandoRequest(CreateMutationRequest[Glissando]):
    """A request to create a glissando from ``start_note`` to ``end_note``."""

    axis: ClassVar[Axis | None] = Axis.RELATIONS
    creates: ClassVar[type[ScoreEntity]] = Glissando

    start_note: Note
    end_note: Note
    glissando_type: GlissandoType
