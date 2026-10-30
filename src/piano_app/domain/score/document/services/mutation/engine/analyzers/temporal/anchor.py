from collections.abc import Sequence
from itertools import chain

from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import find_anchor_at
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.actions.temporal import (
    CreateTemporalAnchorAction,
    UpdateTemporalAnchorAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    Deletable,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.temporal import (
    CreateTemporalAnchorRequest,
    UpdateTemporalAnchorRequest,
)


class CreateTemporalAnchorAnalyzer:
    """Creates the anchor at the requested measure position.

    Mirrors the measure's own guard as a reject: a position at or past the end of the
    measure rejects the request. A position is storage shared by everything starting
    there, so whoever needs one finds the anchor already standing there before asking for
    a new one; asking where one stands is a broken order.
    """

    def analyze(
        self,
        *,
        request: CreateTemporalAnchorRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        if not request.measure.holds(position=request.position):
            raise MutationRejectedError("Position lies at or past the end of the measure.")

        if find_anchor_at(measure=request.measure, position=request.position) is not None:
            raise ValueError("An anchor already stands here: it is found, not created.")

        yield CreateTemporalAnchorAction(
            measure=request.measure,
            position=request.position,
        )


def cascade_anchor(*, target: TemporalAnchor) -> Sequence[Deletable]:
    """Decides the temporal anchor's deletion cascade.

    Every rhythmic container starting here is deleted before the anchor; attached
    contexts are not handled yet.
    """
    # decided before the first deletion: each one detaches its containers from the anchor
    # and from their parents, which the nesting check reads
    containers: Sequence[RhythmicContainer] = target.containers
    outermost: list[RhythmicContainer] = []
    for container in containers:
        # nested containers starting here too are removed by their parent's cascade
        if isinstance(container.parent, GroupRhythmicContainer) and container.parent in containers:
            continue

        outermost.append(container)

    doomed: list[Deletable] = []
    for container in outermost:
        if isinstance(container, LeafRhythmicContainer | GroupRhythmicContainer):
            doomed.append(container)
        else:
            raise ValueError(f"Unknown container type: {type(container)}")

    # TODO later
    for _context in chain(target.starting_contexts, target.ending_contexts):
        pass

    return doomed


class UpdateTemporalAnchorAnalyzer:
    """Moves an anchor to another measure position; everything starting or ending at it
    moves with it and keeps its identity.

    Mirrors the measure's own guard as a reject: a position at or past the end of the
    target measure rejects the request. Another anchor already at that position is a
    broken order, not a choice: whoever moves anchors frees each place before it is taken.
    """

    def analyze(
        self,
        *,
        request: UpdateTemporalAnchorRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        anchor: TemporalAnchor = request.target

        if not request.measure.holds(position=request.position):
            raise MutationRejectedError("Position lies at or past the end of the measure.")

        existing: TemporalAnchor | None = find_anchor_at(
            measure=request.measure,
            position=request.position,
        )
        if existing is not None and existing is not anchor:
            raise ValueError(
                "An anchor is moved to a place another anchor still takes: it must be freed first."
            )

        yield UpdateTemporalAnchorAction(
            target=anchor,
            measure=request.measure,
            position=request.position,
        )
