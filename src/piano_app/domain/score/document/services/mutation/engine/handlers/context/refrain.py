from piano_app.domain.score.document.models.context import Refrain
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateRefrainAction,
    UpdateRefrainEndAction,
    UpdateRefrainStartAction,
    UpdateRefrainTimesAction,
)


class CreateRefrainHandler:
    """Creates a refrain on its anchors."""

    def handle(self, *, action: CreateRefrainAction, sink: MutationSink) -> Refrain:
        return Refrain.create(start=action.start, end=action.end, times=action.times, sink=sink)


class UpdateRefrainTimesHandler:
    """Changes how many times a refrain is played."""

    def handle(self, *, action: UpdateRefrainTimesAction, sink: MutationSink) -> None:
        action.target.set_times(times=action.times, sink=sink)
        return None


class UpdateRefrainStartHandler:
    """Moves a refrain's start to another anchor."""

    def handle(self, *, action: UpdateRefrainStartAction, sink: MutationSink) -> None:
        action.target.set_start(start=action.start, sink=sink)
        return None


class UpdateRefrainEndHandler:
    """Moves a refrain's end to another anchor, or to the end of the score."""

    def handle(self, *, action: UpdateRefrainEndAction, sink: MutationSink) -> None:
        action.target.set_end(end=action.end, sink=sink)
        return None
