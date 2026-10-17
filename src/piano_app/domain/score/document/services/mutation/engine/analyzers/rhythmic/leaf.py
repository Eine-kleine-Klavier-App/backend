from piano_app.domain.score.document.models.material import NoteCarrier, RestCarrier
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    LeafRhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.rhythmic.room import (
    make_room,
)
from piano_app.domain.score.document.services.mutation.engine.buffer import EmitBuffer
from piano_app.domain.score.document.services.mutation.engine.resolver import ResolveBound
from piano_app.domain.score.document.services.mutation.instructions import Bound
from piano_app.domain.score.document.services.mutation.instructions.actions.rhythmic import (
    CreateLeafAction,
    DeleteLeafAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    DeleteNoteCarrierRequest,
    DeleteRestCarrierRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    CreateLeafRequest,
    DeleteLeafRequest,
)


class CreateLeafAnalyzer:
    """Decides placement and displacement for a new metric leaf.

    The leaf goes into the scope the request names — it never descends on its own, so
    every piece of a sliced note stays in the scope its note was placed in. Spilling
    across that scope rejects the request. The anchor is reused or created, and
    intersecting sibling containers are deleted before the leaf is created.
    """

    def analyze(
        self,
        *,
        request: CreateLeafRequest,
        resolver: ResolveBound,
    ) -> EmitBuffer:
        buffer: EmitBuffer = EmitBuffer(request=request)
        # the scope may be a group created earlier in the same gesture
        scope: RhythmicContainerParent = resolver(request.scope)

        anchor: Bound[TemporalAnchor] = make_room(
            buffer=buffer,
            scope=scope,
            measure=request.measure,
            position=request.position,
            size=request.size,
        )

        buffer.incorporate(
            item=CreateLeafAction(
                parent=scope,
                anchor=anchor,
                size=request.size,
                out=request.out,
            ),
        )

        return buffer


class DeleteLeafAnalyzer:
    """Decides the metric leaf's deletion cascade.

    An attached note or rest carrier is deleted before the leaf; grace-group
    deletion is not implemented yet.
    """

    def analyze(
        self,
        *,
        request: DeleteLeafRequest,
        resolver: ResolveBound,
    ) -> EmitBuffer:
        buffer: EmitBuffer = EmitBuffer(request=request)
        leaf: LeafRhythmicContainer = request.target

        # TODO later
        if leaf.grace_before is not None:
            pass

        if leaf.grace_after is not None:
            pass

        carrier = leaf.carrier
        if carrier is not None:
            if isinstance(carrier, NoteCarrier):
                buffer.incorporate(item=DeleteNoteCarrierRequest(target=carrier))
            elif isinstance(carrier, RestCarrier):
                buffer.incorporate(item=DeleteRestCarrierRequest(target=carrier))
            else:
                raise ValueError(f"Unknown carrier type: {type(carrier)}")

        buffer.incorporate(item=DeleteLeafAction(target=leaf))

        return buffer
