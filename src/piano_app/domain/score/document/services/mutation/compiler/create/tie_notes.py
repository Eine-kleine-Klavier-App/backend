from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.relations.start_end import Tie
from piano_app.domain.score.document.services.mutation.compiler.intents import TieNotesIntent
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRequest,
    ResultRef,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    CreateTieRequest,
)


class TieNotesCompiler:
    """Compiles a tie between two existing notes into a single tie request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: TieNotesIntent,
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

        return [CreateTieRequest(start_note=start_note, end_note=end_note, out=ResultRef[Tie]())]
