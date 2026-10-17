from dataclasses import dataclass

from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class TieNotesIntent(EditIntent):
    start_note_id: str
    end_note_id: str
