from piano_app.domain.score.document.models.context import SustainHold
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateSustainHoldAction,
)


class CreateSustainHoldHandler:
    """Creates a sustain hold on its anchors."""

    def handle(
        self,
        *,
        action: CreateSustainHoldAction,
        sink: MutationSink,
    ) -> SustainHold:
        return SustainHold.create(start=action.start, end=action.end, sink=sink)
