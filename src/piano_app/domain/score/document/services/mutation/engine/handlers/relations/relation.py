from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.models.relations import Relation
from piano_app.domain.score.document.services.mutation.instructions.actions.relations import (
    DeleteRelationAction,
    UpdateRelationStartAction,
)


class DeleteRelationHandler:
    """Detaches a relation from its peers."""

    def handle(
        self,
        *,
        action: DeleteRelationAction,
        sink: MutationSink,
    ) -> None:
        relation: Relation = action.target
        relation.detach(sink=sink)
        return None


class UpdateRelationStartHandler:
    """Moves a note-to-note relation's start to another note."""

    def handle(
        self,
        *,
        action: UpdateRelationStartAction,
        sink: MutationSink,
    ) -> None:
        action.target.set_start(start_note=action.start_note, sink=sink)
        return None
