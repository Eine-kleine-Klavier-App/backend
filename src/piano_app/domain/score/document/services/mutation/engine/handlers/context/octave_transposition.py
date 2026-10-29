from piano_app.domain.score.document.models.context import OctaveTransposition
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateOctaveTranspositionAction,
)


class CreateOctaveTranspositionHandler:
    """Creates an octave transposition on its anchors."""

    def handle(
        self,
        *,
        action: CreateOctaveTranspositionAction,
        sink: MutationSink,
    ) -> OctaveTransposition:
        start: TemporalAnchor = action.start
        end: TemporalAnchor = action.end
        return OctaveTransposition.create(
            start=start,
            end=end,
            staff=action.staff,
            octaves=action.octaves,
            sink=sink,
        )
