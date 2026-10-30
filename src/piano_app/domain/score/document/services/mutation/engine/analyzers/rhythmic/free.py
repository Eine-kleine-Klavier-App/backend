from collections.abc import Sequence

from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)


def free_room(*, met: Sequence[RhythmicContainer]) -> MutationAnalysis:
    """Removes what a new span meets, each container once, in the order given: a leaf with
    its content, a group whole with everything in it."""
    freed: list[RhythmicContainer] = []
    for container in met:
        if any(container is other for other in freed):
            continue

        freed.append(container)

        if isinstance(container, LeafRhythmicContainer | GroupRhythmicContainer):
            yield DeleteRequest(target=container)
        else:
            raise ValueError(f"Unknown container type: {type(container)}")
