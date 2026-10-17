from collections.abc import Sequence
from itertools import chain

from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
)
from piano_app.domain.score.document.services.helpers import find_anchor_at
from piano_app.domain.score.document.services.mutation.engine.buffer import EmitBuffer
from piano_app.domain.score.document.services.mutation.engine.resolver import ResolveBound
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.actions.temporal import (
    CreateTemporalAnchorAction,
    DeleteTemporalAnchorAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    DeleteLeafRequest,
    DeleteRhythmicGroupRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.temporal import (
    CreateTemporalAnchorRequest,
    DeleteTemporalAnchorRequest,
)


class CreateTemporalAnchorAnalyzer:
    """Decides whether an anchor may be created at the requested measure position.

    Mirrors the measure's own guards as rejects: a position at or past the end of the
    measure, or an existing anchor at that exact position, rejects the request;
    otherwise a new anchor is created.
    """

    def analyze(
        self,
        *,
        request: CreateTemporalAnchorRequest,
        resolver: ResolveBound,
    ) -> EmitBuffer:
        buffer: EmitBuffer = EmitBuffer(request=request)

        if not request.measure.holds(position=request.position):
            raise MutationRejectedError("Position lies at or past the end of the measure.")

        # check if anchor already exists at requested position
        if (
            find_anchor_at(
                measure=request.measure,
                position=request.position,
            )
            is not None
        ):
            raise MutationRejectedError("Anchor already exists.")

        buffer.incorporate(
            item=CreateTemporalAnchorAction(
                measure=request.measure,
                position=request.position,
                out=request.out,
            ),
        )

        return buffer


class DeleteTemporalAnchorAnalyzer:
    """Decides the temporal anchor's deletion cascade.

    Every rhythmic container starting here is deleted before the anchor; attached
    contexts are not handled yet.
    """

    def analyze(
        self,
        *,
        request: DeleteTemporalAnchorRequest,
        resolver: ResolveBound,
    ) -> EmitBuffer:
        buffer: EmitBuffer = EmitBuffer(request=request)
        anchor: TemporalAnchor = request.target

        containers: Sequence[RhythmicContainer] = anchor.containers
        for container in containers:
            # nested containers starting here too are removed by their parent's cascade
            if container.parent in containers:
                continue

            if isinstance(container, LeafRhythmicContainer):
                buffer.incorporate(item=DeleteLeafRequest(target=container))
            elif isinstance(container, GroupRhythmicContainer):
                buffer.incorporate(item=DeleteRhythmicGroupRequest(target=container))
            else:
                raise ValueError(f"Unknown container type: {type(container)}")

        # TODO later
        for _context in chain(anchor.starting_contexts, anchor.ending_contexts):
            pass

        buffer.incorporate(item=DeleteTemporalAnchorAction(target=anchor))

        return buffer
