from piano_app.domain.score.document.models.material import Carrier, NoteCarrier, RestCarrier
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
)
from piano_app.domain.score.document.services.helpers import iter_leaves


def holds_content(*, container: RhythmicContainer) -> bool:
    """Whether a note or a rest sits anywhere inside the container.

    Content is judged at the lowest level — the notes and rests themselves — never by
    the containers: a leaf whose carrier is gone or empty, or a group of such leaves, is
    mid-gesture scaffolding, not content.
    """
    leaves: list[LeafRhythmicContainer]
    if isinstance(container, LeafRhythmicContainer):
        leaves = [container]
    elif isinstance(container, GroupRhythmicContainer):
        leaves = iter_leaves(container)
    else:
        raise TypeError(f"Unsupported rhythmic container type: {type(container).__name__}.")

    for leaf in leaves:
        carrier: Carrier | None = leaf.carrier
        if isinstance(carrier, NoteCarrier) and carrier.notes:
            return True
        if isinstance(carrier, RestCarrier) and carrier.rest is not None:
            return True

    return False
