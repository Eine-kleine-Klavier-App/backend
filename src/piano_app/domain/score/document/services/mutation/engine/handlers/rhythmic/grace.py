from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.models.structural.rhythm import GraceGroup, GraceItem
from piano_app.domain.score.document.services.mutation.instructions.actions.rhythmic import (
    CreateGraceGroupAction,
    CreateGraceItemAction,
    DeleteGraceGroupAction,
    DeleteGraceItemAction,
    UpdateGraceTypeAction,
    UpdateGraceValueAction,
)


class CreateGraceGroupHandler:
    """Creates a group of grace notes on its leaf."""

    def handle(self, *, action: CreateGraceGroupAction, sink: MutationSink) -> GraceGroup:
        return GraceGroup.create(
            leaf=action.leaf,
            grace_type=action.grace_type,
            placement=action.placement,
            sink=sink,
        )


class CreateGraceItemHandler:
    """Creates a grace item in its group, at its index or at the end."""

    def handle(self, *, action: CreateGraceItemAction, sink: MutationSink) -> GraceItem:
        return GraceItem.create(
            grace_group=action.group,
            rhythmic_value=action.rhythmic_value,
            index=action.index,
            sink=sink,
        )


class DeleteGraceGroupHandler:
    """Detaches a group of grace notes from its leaf."""

    def handle(self, *, action: DeleteGraceGroupAction, sink: MutationSink) -> None:
        action.target.detach(sink=sink)
        return None


class DeleteGraceItemHandler:
    """Detaches a grace item from its group."""

    def handle(self, *, action: DeleteGraceItemAction, sink: MutationSink) -> None:
        action.target.detach(sink=sink)
        return None


class UpdateGraceTypeHandler:
    """Sets the kind of a group of grace notes."""

    def handle(self, *, action: UpdateGraceTypeAction, sink: MutationSink) -> None:
        action.target.set_grace_type(grace_type=action.grace_type, sink=sink)
        return None


class UpdateGraceValueHandler:
    """Writes a grace item as another value."""

    def handle(self, *, action: UpdateGraceValueAction, sink: MutationSink) -> None:
        action.target.set_rhythmic_value(rhythmic_value=action.rhythmic_value, sink=sink)
        return None
