from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.models.relations import Tie
from piano_app.domain.score.document.services.mutation.instructions.actions.relations import (
    CreateTieAction,
)


class CreateTieHandler:
    """Creates a tie between two notes."""

    def handle(
        self,
        *,
        action: CreateTieAction,
        sink: MutationSink,
    ) -> Tie:
        start_note: Note = action.start_note
        end_note: Note = action.end_note
        relation: Tie = Tie.create(
            start_note=start_note,
            end_note=end_note,
            sink=sink,
        )
        return relation
