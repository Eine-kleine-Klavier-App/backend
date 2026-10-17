from piano_app.domain.score.document.models.context import OctaveTransposition
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.services.mutation.engine.resolver import ResolveBound
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateOctaveTranspositionAction,
)


class CreateOctaveTranspositionHandler:
    """Creates an octave transposition on its anchors (resolved from the environment)."""

    def handle(
        self,
        *,
        action: CreateOctaveTranspositionAction,
        resolve: ResolveBound,
        sink: MutationSink,
    ) -> OctaveTransposition:
        start: TemporalAnchor = resolve(action.start)
        end: TemporalAnchor = resolve(action.end)
        return OctaveTransposition.create(
            start=start,
            end=end,
            staff=action.staff,
            octaves=action.octaves,
            sink=sink,
        )
