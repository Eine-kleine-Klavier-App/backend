from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Carrier
from piano_app.domain.score.document.models.relations import Beam
from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation.compiler.intents import SplitBeamIntent
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    SplitBeamRequest,
)


class SplitBeamCompiler:
    """Addresses the relation and the carrier; the analyzer decides the split on the live beam."""

    def compile(
        self, *, document: ScoreDocument, intent: SplitBeamIntent, entities: EntityIndex
    ) -> Sequence[MutationRequest]:
        entities_by_id = resolve_entities(
            entities=entities, entity_ids=(intent.beam_id, intent.before_carrier_id)
        )
        beam = expect_entity(entities_by_id=entities_by_id, entity_id=intent.beam_id, expected=Beam)
        carrier = expect_entity(
            entities_by_id=entities_by_id, entity_id=intent.before_carrier_id, expected=Carrier
        )
        return [SplitBeamRequest(target=beam, before_carrier=carrier)]
