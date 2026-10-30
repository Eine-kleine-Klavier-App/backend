from piano_app.domain.score.document.models.material import CarrierOwner, RestCarrier
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.services.mutation.instructions.actions.material import (
    CreateRestCarrierAction,
    DeleteRestCarrierAction,
)


class CreateRestCarrierHandler:
    """Creates a rest carrier on its owner."""

    def handle(
        self,
        *,
        action: CreateRestCarrierAction,
        sink: MutationSink,
    ) -> RestCarrier:
        owner: CarrierOwner = action.owner
        carrier: RestCarrier = RestCarrier.create(
            owner=owner,
            sink=sink,
        )
        return carrier


class DeleteRestCarrierHandler:
    """Detaches a rest carrier from its owner."""

    def handle(
        self,
        *,
        action: DeleteRestCarrierAction,
        sink: MutationSink,
    ) -> None:
        rest_carrier: RestCarrier = action.target
        rest_carrier.detach(sink=sink)
        return None
