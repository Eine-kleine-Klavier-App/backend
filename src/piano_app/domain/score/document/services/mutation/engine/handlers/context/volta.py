from piano_app.domain.score.document.models.context import Volta
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateVoltaAction,
    ReshapeVoltaAction,
)


class CreateVoltaHandler:
    """Creates a volta on its anchors."""

    def handle(self, *, action: CreateVoltaAction, sink: MutationSink) -> Volta:
        return Volta.create(
            start=action.start,
            body_end=action.body_end,
            fragments=action.fragments,
            sink=sink,
        )


class ReshapeVoltaHandler:
    """Gives a volta another body and other fragments."""

    def handle(self, *, action: ReshapeVoltaAction, sink: MutationSink) -> None:
        action.target.reshape(
            start=action.start,
            body_end=action.body_end,
            fragments=action.fragments,
            sink=sink,
        )
        return None
