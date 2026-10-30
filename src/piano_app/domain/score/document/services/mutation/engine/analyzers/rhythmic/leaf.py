from collections.abc import Sequence

from piano_app.domain.score.document.models.material import Carrier, NoteCarrier, RestCarrier
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    LeafRhythmicContainer,
    RhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import fits
from piano_app.domain.score.document.services.mutation.engine.analyzers.base import (
    find_or_create_anchor,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.rhythmic.room import (
    find_met_containers,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.actions.rhythmic import (
    CreateLeafAction,
    UpdateLeafSizeAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    Deletable,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    CreateLeafRequest,
    UpdateLeafSizeRequest,
)


class CreateLeafAnalyzer:
    """Creates a metric leaf in the scope its request names, at a found or new anchor.

    The leaf never descends on its own, and it displaces nothing: what it would meet was
    removed by whoever placed its spans, so a container of the scope still in its room is
    a broken invariant, not a choice. Spilling across the scope rejects the request.
    """

    def analyze(
        self,
        *,
        request: CreateLeafRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        scope: RhythmicContainerParent = request.scope

        met: list[RhythmicContainer] = find_met_containers(
            geometry=geometry,
            scope=scope,
            measure=request.measure,
            position=request.position,
            size=request.written_size,
        )
        if met:
            raise ValueError(
                f"A new leaf would meet {len(met)} container(s) of its scope: its room must "
                "be cleared before it is created."
            )

        anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=request.measure, position=request.position
        )

        yield CreateLeafAction(
            parent=scope,
            anchor=anchor,
            size=request.written_size,
        )


def cascade_leaf(*, target: LeafRhythmicContainer) -> Sequence[Deletable]:
    """Decides the metric leaf's deletion cascade.

    The groups of grace notes before and after it and an attached note or rest carrier are
    deleted before the leaf.
    """
    doomed: list[Deletable] = []
    if target.grace_before is not None:
        doomed.append(target.grace_before)

    if target.grace_after is not None:
        doomed.append(target.grace_after)

    carrier: Carrier | None = target.carrier
    if carrier is not None:
        if isinstance(carrier, NoteCarrier | RestCarrier):
            doomed.append(carrier)
        else:
            raise ValueError(f"Unknown carrier type: {type(carrier)}")

    return doomed


class UpdateLeafSizeAnalyzer:
    """Resizes a metric leaf in place; its carrier, its content and its anchor stay.

    Like a new leaf, it displaces nothing: what its new room would meet was removed by
    whoever resized its span, so another container of its scope still there is a broken
    invariant. Spilling across the scope rejects the request.
    """

    def analyze(
        self,
        *,
        request: UpdateLeafSizeRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        leaf: LeafRhythmicContainer = request.target

        met: list[RhythmicContainer] = [
            container
            for container in find_met_containers(
                geometry=geometry,
                scope=leaf.parent,
                measure=leaf.anchor.measure,
                position=leaf.anchor.position,
                size=request.written_size,
            )
            if container is not leaf
        ]
        if met:
            raise ValueError(
                f"A resized leaf would meet {len(met)} container(s) of its scope: its room "
                "must be cleared before it is resized."
            )

        # the grace notes of the leaf take their time from it: it cannot shrink below what they take
        if not fits(leaf=leaf, length=request.written_size.fraction):
            raise MutationRejectedError(
                "The leaf's grace notes would no longer fit in the time it is resized to."
            )

        yield UpdateLeafSizeAction(target=leaf, size=request.written_size)
