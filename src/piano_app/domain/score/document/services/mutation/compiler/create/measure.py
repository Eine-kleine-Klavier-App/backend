from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.structural import Measure
from piano_app.domain.score.document.services.helpers import neighbour_signature
from piano_app.domain.score.document.services.mutation.compiler.intents import (
    AppendMeasureIntent,
    InsertMeasureIntent,
)
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CloseOpenContextEndsRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.intent import (
    InsertMeasureRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.structural import (
    CreateEmptyMeasureRequest,
)


class AppendMeasureCompiler:
    """Compiles adding a measure after the last one into a create request, with the time
    signature of the last measure read on the live document, and one that keeps every span that
    lasted until the end of the score where it was (it would otherwise cover the new measure)."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: AppendMeasureIntent,
    ) -> Sequence[MutationRequest]:
        return [
            CreateEmptyMeasureRequest(
                document=document,
                before=None,
                time_signature=neighbour_signature(document=document, before=None),
            ),
            CloseOpenContextEndsRequest(document=document),
        ]


class InsertMeasureCompiler:
    """Compiles adding a measure before a given one into one insert request; its time
    signature, the groups split at its barline, the relations it breaks and the contexts
    carried over at the start of the score are decided on the live document."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: InsertMeasureIntent,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document,
            entity_ids=(intent.before_measure_id,),
        )
        before: Measure = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.before_measure_id,
            expected=Measure,
        )

        return [InsertMeasureRequest(document=document, before=before)]
