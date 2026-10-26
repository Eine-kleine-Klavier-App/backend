from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.services.mutation.compiler.intents import (
    GlissandoNotesIntent,
)
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    CreateGlissandoRequest,
)


class GlissandoNotesCompiler:
    """Compiles a glissando between two existing notes into a glissando request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: GlissandoNotesIntent,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document,
            entity_ids=(intent.start_note_id, intent.end_note_id),
        )
        start_note: Note = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.start_note_id,
            expected=Note,
        )
        end_note: Note = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.end_note_id,
            expected=Note,
        )

        return [
            CreateGlissandoRequest(
                start_note=start_note,
                end_note=end_note,
                glissando_type=intent.glissando_type,
            )
        ]
