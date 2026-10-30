from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    LeafRhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.rhythmic import (
    CreateLeafAction,
    DeleteLeafAction,
    UpdateLeafSizeAction,
)


class CreateLeafHandler:
    """Creates a leaf rhythmic container, at its anchor and inside its optional
    parent group."""

    def handle(
        self,
        *,
        action: CreateLeafAction,
        sink: MutationSink,
    ) -> LeafRhythmicContainer:
        anchor: TemporalAnchor = action.anchor
        parent: RhythmicContainerParent = action.parent

        leaf: LeafRhythmicContainer = LeafRhythmicContainer.create(
            parent=parent,
            anchor=anchor,
            size=action.size,
            sink=sink,
        )
        return leaf


class DeleteLeafHandler:
    """Detaches a leaf from its parent scope."""

    def handle(
        self,
        *,
        action: DeleteLeafAction,
        sink: MutationSink,
    ) -> None:
        leaf: LeafRhythmicContainer = action.target
        leaf.detach(sink=sink)
        return None


class UpdateLeafSizeHandler:
    """Resizes a leaf rhythmic container in place."""

    def handle(
        self,
        *,
        action: UpdateLeafSizeAction,
        sink: MutationSink,
    ) -> None:
        leaf: LeafRhythmicContainer = action.target
        leaf.set_size(size=action.size, sink=sink)
        return None
