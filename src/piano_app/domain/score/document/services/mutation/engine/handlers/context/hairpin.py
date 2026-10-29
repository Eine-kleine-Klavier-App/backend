from piano_app.domain.score.document.models.context import Hairpin
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.services.mutation.instructions.actions.context import (
    CreateHairpinAction,
    UpdateHairpinStepsAction,
)


class CreateHairpinHandler:
    """Creates a hairpin on its anchors."""

    def handle(
        self,
        *,
        action: CreateHairpinAction,
        sink: MutationSink,
    ) -> Hairpin:
        return Hairpin.create(
            start=action.start,
            end=action.end,
            voices=list(action.voices),
            steps=action.steps,
            sink=sink,
        )


class UpdateHairpinStepsHandler:
    """Changes by how many dynamic levels a hairpin moves."""

    def handle(
        self,
        *,
        action: UpdateHairpinStepsAction,
        sink: MutationSink,
    ) -> None:
        action.target.set_steps(steps=action.steps, sink=sink)
        return None
