from piano_app.domain.score.document.models.context import TempoTransition
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateTempoTransitionAction,
    UpdateTempoTransitionRatioAction,
)


class CreateTempoTransitionHandler:
    """Creates a tempo transition on its anchors."""

    def handle(
        self,
        *,
        action: CreateTempoTransitionAction,
        sink: MutationSink,
    ) -> TempoTransition:
        return TempoTransition.create(
            start=action.start,
            end=action.end,
            ratio=action.ratio,
            sink=sink,
        )


class UpdateTempoTransitionRatioHandler:
    """Changes the ratio of speed a tempo transition ends at."""

    def handle(
        self,
        *,
        action: UpdateTempoTransitionRatioAction,
        sink: MutationSink,
    ) -> None:
        action.target.set_ratio(ratio=action.ratio, sink=sink)
        return None
