from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.services.mutation.compiler.intents import (
    SetFingeringIntent,
)
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    UpdateFingeringRequest,
)


class SetFingeringCompiler:
    """Compiles a fingering on one note into a single update request."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: SetFingeringIntent,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document,
            entity_ids=(intent.note_id,),
        )
        note: Note = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.note_id,
            expected=Note,
        )

        return [UpdateFingeringRequest(target=note, fingering=intent.fingering)]
