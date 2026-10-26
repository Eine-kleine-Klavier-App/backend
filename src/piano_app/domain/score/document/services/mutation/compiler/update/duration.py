from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.material import Carrier, CarrierOwner
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.mutation.compiler.intents import (
    ChangeDurationIntent,
)
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    ResizeSpanRequest,
)


class ChangeDurationCompiler:
    """Compiles a new written value for one note or rest carrier into one request: its
    leaf's span is resized — in place, cut at the barlines when it must be — against the
    document that left; whatever the new span meets goes with it.

    A grace carrier is refused: it has no span of its own.
    """

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: ChangeDurationIntent,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document,
            entity_ids=(intent.carrier_id,),
        )
        carrier: Carrier = expect_entity(
            entities_by_id=entities_by_id,
            entity_id=intent.carrier_id,
            expected=Carrier,
        )

        owner: CarrierOwner = carrier.owner
        if not isinstance(owner, LeafRhythmicContainer):
            raise MutationRejectedError("A grace element's duration cannot be changed.")

        return [ResizeSpanRequest(leaf=owner, written_value=intent.written_value)]
