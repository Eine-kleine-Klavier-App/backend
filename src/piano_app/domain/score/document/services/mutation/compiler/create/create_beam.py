from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.material import Carrier
from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation.compiler.intents import CreateBeamIntent
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    CreateBeamRequest,
)


class CreateBeamCompiler:
    """Compiles beaming the listed carriers into a single beam request; whether they may be
    beamed is decided on the live document."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: CreateBeamIntent,
        entities: EntityIndex,
    ) -> Sequence[MutationRequest]:
        # a repeated id would make the beam hold one carrier twice
        carrier_ids: tuple[str, ...] = tuple(dict.fromkeys(intent.carrier_ids))
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            entities=entities,
            entity_ids=carrier_ids,
        )
        carriers: tuple[Carrier, ...] = tuple(
            expect_entity(entities_by_id=entities_by_id, entity_id=carrier_id, expected=Carrier)
            for carrier_id in carrier_ids
        )

        return [CreateBeamRequest(carriers=carriers)]
