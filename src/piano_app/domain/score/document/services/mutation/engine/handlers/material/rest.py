from piano_app.domain.score.document.models.material import Rest, RestCarrier
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.services.mutation.instructions.actions.material import (
    CreateRestAction,
    DeleteRestAction,
)


class CreateRestHandler:
    """Creates a rest inside its carrier."""

    def handle(
        self,
        *,
        action: CreateRestAction,
        sink: MutationSink,
    ) -> Rest:
        rest_carrier: RestCarrier = action.rest_carrier
        rest: Rest = Rest.create(
            rest_carrier=rest_carrier,
            staff=action.staff,
            sink=sink,
        )
        return rest


class DeleteRestHandler:
    """Detaches a rest from its carrier."""

    def handle(
        self,
        *,
        action: DeleteRestAction,
        sink: MutationSink,
    ) -> None:
        rest: Rest = action.target
        rest.detach(sink=sink)
        return None
