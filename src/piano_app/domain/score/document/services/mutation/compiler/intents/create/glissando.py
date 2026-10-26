from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import GlissandoType
from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class GlissandoNotesIntent(EditIntent):
    start_note_id: str
    end_note_id: str
    glissando_type: GlissandoType
