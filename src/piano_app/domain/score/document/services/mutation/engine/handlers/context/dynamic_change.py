from piano_app.domain.score.document.models.context import DynamicChange
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateDynamicChangeAction,
)


class CreateDynamicChangeHandler:
    """Creates a dynamic change on its anchor."""

    def handle(
        self,
        *,
        action: CreateDynamicChangeAction,
        sink: MutationSink,
    ) -> DynamicChange:
        return DynamicChange.create(
            start=action.start,
            voices=list(action.voices),
            dynamic=action.dynamic,
            sink=sink,
        )
