from piano_app.domain.score.document.models.context import Slur
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateSlurAction,
)


class CreateSlurHandler:
    """Creates a slur on its anchors."""

    def handle(
        self,
        *,
        action: CreateSlurAction,
        sink: MutationSink,
    ) -> Slur:
        return Slur.create(
            start=action.start,
            end=action.end,
            voices=list(action.voices),
            sink=sink,
        )
