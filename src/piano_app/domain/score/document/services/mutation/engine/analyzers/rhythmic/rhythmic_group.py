from collections.abc import Sequence

from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.geometry import Span
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.analyzers.base import (
    find_or_create_anchor,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.rhythmic.free import (
    free_room,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.rhythmic.room import (
    locate_item,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.rhythmic import (
    CreateRhythmicGroupAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    Deletable,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    CreateRhythmicGroupRequest,
)


class CreateRhythmicGroupAnalyzer:
    """Decides placement and displacement for a new, empty rhythmic group.

    Located like any item on the live document — in the deepest scope of its voice
    holding its start, refused when the start lies outside its measure or the group does
    not fit there — and never cut at a barline, since a group spans barlines on its own.
    Placed at a found or new anchor, displacing the containers of that scope it meets — a
    frame may remove the frames and spans below it. Its interior is left empty — the fill
    postprocessor tiles it with rests at the gesture boundary.
    """

    def analyze(
        self,
        *,
        request: CreateRhythmicGroupRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        # what the group takes is read in the scope it lands in
        scope: RhythmicContainerParent
        span: Span
        scope, span = locate_item(
            geometry=geometry,
            voice=request.voice,
            measure=request.measure,
            position=request.position,
            written_length=request.occupied_size.fraction,
        )

        # mirrors the group's own guard: a group that scales nothing is refused, not a crash
        if request.written_size.fraction == request.occupied_size.fraction:
            raise MutationRejectedError("A group must differ in written and occupied size.")

        # decided before the first yield; only the scope and the met containers are
        # carried across
        met: list[RhythmicContainer] = [
            meeting.region for meeting in geometry.intersecting(span=span, scope=scope)
        ]

        anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.measure, position=request.position
        )

        yield from free_room(met=met)

        yield CreateRhythmicGroupAction(
            parent=scope,
            anchor=anchor,
            written_size=request.written_size,
            occupied_size=request.occupied_size,
        )


def cascade_group(*, target: GroupRhythmicContainer) -> Sequence[Deletable]:
    """Decides the rhythmic group's deletion cascade.

    Every direct leaf and subgroup triggers its own deletion before the group.
    """
    # a snapshot: each child's deletion removes it from the group's own list
    children: list[RhythmicContainer] = list(target.children)

    doomed: list[Deletable] = []
    for child in children:
        if isinstance(child, LeafRhythmicContainer | GroupRhythmicContainer):
            doomed.append(child)
        else:
            raise ValueError(f"Unknown container type: {type(child)}")

    return doomed
