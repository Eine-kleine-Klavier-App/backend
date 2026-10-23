from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.structural import Voice
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceItem,
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
)
from piano_app.domain.score.document.models.structural.rhythm.metric.parent import (
    RhythmicContainerParent,
)


def iter_leaves(
    parent: RhythmicContainerParent,
) -> list[LeafRhythmicContainer]:
    flattened: list[LeafRhythmicContainer] = []
    for child in parent.children:
        if isinstance(child, LeafRhythmicContainer):
            flattened.append(child)
        elif isinstance(child, GroupRhythmicContainer):
            flattened.extend(iter_leaves(child))
        else:
            raise TypeError(f"Unsupported rhythmic container type: {type(child).__name__}.")

    return flattened


def voice_of(
    container: RhythmicContainer,
) -> Voice:
    if isinstance(container.parent, Voice):
        return container.parent

    if isinstance(container.parent, GroupRhythmicContainer):
        return voice_of(container.parent)

    raise TypeError("Rhythmic container parent is not a voice.")


def host_leaf_of(*, note: Note) -> LeafRhythmicContainer | None:
    """The leaf a note sounds with: the leaf holding its carrier, or for a grace note the leaf
    its group belongs to."""
    owner: object = note.note_carrier.owner
    if isinstance(owner, GraceItem):
        return owner.grace_group.leaf

    return owner if isinstance(owner, LeafRhythmicContainer) else None
