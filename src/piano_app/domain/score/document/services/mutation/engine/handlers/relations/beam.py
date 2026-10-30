from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.models.relations import Beam
from piano_app.domain.score.document.services.mutation.instructions.actions.relations import (
    CreateBeamAction,
    UpdateBeamMembersAction,
)


class UpdateBeamMembersHandler:
    """Keeps a beam on a run of its consecutive members only."""

    def handle(
        self,
        *,
        action: UpdateBeamMembersAction,
        sink: MutationSink,
    ) -> None:
        action.target.narrow_to(carriers=action.carriers, sink=sink)
        return None


class CreateBeamHandler:
    """Creates a beam over carriers."""

    def handle(
        self,
        *,
        action: CreateBeamAction,
        sink: MutationSink,
    ) -> Beam:
        return Beam.create(carriers=list(action.carriers), sink=sink)
