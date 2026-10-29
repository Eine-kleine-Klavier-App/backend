from piano_app.domain.score.document.models.context import TempoChange
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateTempoChangeAction,
)


class CreateTempoChangeHandler:
    """Creates a tempo change on its anchor."""

    def handle(
        self,
        *,
        action: CreateTempoChangeAction,
        sink: MutationSink,
    ) -> TempoChange:
        return TempoChange.create(
            start=action.start,
            beat=action.beat,
            bpm=action.bpm,
            show_label=action.show_label,
            sink=sink,
        )
