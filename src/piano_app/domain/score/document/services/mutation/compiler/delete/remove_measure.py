from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.structural import Measure
from piano_app.domain.score.document.services.mutation.compiler.intents import RemoveMeasureIntent
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest
from piano_app.domain.score.document.services.mutation.instructions.requests.intent import (
    RemoveRequest,
)


class RemoveMeasureCompiler:
    """Compiles removing one measure into the remove request a delete batch naming it
    compiles to, so both follow the same removal rules on the live document."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: RemoveMeasureIntent,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document,
            entity_ids=(intent.measure_id,),
        )
        measure: Measure = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.measure_id,
            expected=Measure,
        )

        return [RemoveRequest(document=document, targets=(measure,))]
