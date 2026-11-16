from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation.compiler.intents import (
    SetOrnamentIntent,
)
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    UpdateOrnamentRequest,
)


class SetOrnamentCompiler:
    """Compiles an ornament on one note carrier into a single update request; a rest
    carrier has no ornament and is refused."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: SetOrnamentIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=(intent.carrier_id,),
        )
        carrier: NoteCarrier = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.carrier_id,
            expected=NoteCarrier,
        )

        return [UpdateOrnamentRequest(target=carrier, ornament=intent.ornament)]
