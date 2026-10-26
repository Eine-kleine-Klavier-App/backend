from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.structural import Measure
from piano_app.domain.score.document.services.mutation.compiler.intents import (
    ChangeTimeSignatureIntent,
)
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest
from piano_app.domain.score.document.services.mutation.instructions.requests.intent import (
    ChangeTimeSignatureRequest,
)


class ChangeTimeSignatureCompiler:
    """Compiles a new time signature for the selected measures into one intent request;
    whether the selection is contiguous, and everything it moves, is decided on the live
    document."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: ChangeTimeSignatureIntent,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document,
            entity_ids=intent.measure_ids,
        )
        measures: tuple[Measure, ...] = tuple(
            expect_entity(entities_by_id=entities_by_id, entity_id=measure_id, expected=Measure)
            for measure_id in intent.measure_ids
        )

        return [
            ChangeTimeSignatureRequest(
                document=document,
                measures=measures,
                time_signature=intent.time_signature,
            )
        ]
