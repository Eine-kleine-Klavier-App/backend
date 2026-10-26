from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import Fingering
from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class SetFingeringIntent(EditIntent):
    """Mark this note with a fingering; ``Fingering.NONE`` clears it."""

    note_id: str
    fingering: Fingering
