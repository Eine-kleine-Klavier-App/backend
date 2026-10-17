from piano_app.domain.score.document.models.material import Carrier, Rest, RestCarrier
from piano_app.domain.score.document.models.structural.rhythm import (
    LeafRhythmicContainer,
    RhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.helpers import find_container_at
from piano_app.domain.score.document.services.mutation.engine.buffer import EmitBuffer
from piano_app.domain.score.document.services.mutation.engine.resolver import ResolveBound
from piano_app.domain.score.document.services.mutation.instructions import Bound, ResultRef
from piano_app.domain.score.document.services.mutation.instructions.actions.material import (
    CreateRestAction,
    DeleteRestAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    CreateRestCarrierRequest,
    CreateRestRequest,
    DeleteRestRequest,
)


class CreateRestAnalyzer:
    """Decides where to create a rest in the requested scope slot.

    A same-size leaf with a rest carrier triggers replacement of its rest; every
    other slot state delegates creation of a suitable carrier.
    """

    def analyze(
        self,
        *,
        request: CreateRestRequest,
        resolver: ResolveBound,
    ) -> EmitBuffer:
        buffer: EmitBuffer = EmitBuffer(request=request)
        # the scope may be a group created earlier in the same gesture
        scope: RhythmicContainerParent = resolver(request.scope)

        # only a leaf of the scope can be reused; a group starting there is a sibling the
        # new leaf will displace
        container: RhythmicContainer | None = find_container_at(
            measure=request.measure,
            position=request.position,
            scope=scope,
        )
        leaf: LeafRhythmicContainer | None = (
            container if isinstance(container, LeafRhythmicContainer) else None
        )
        carrier: Carrier | None = leaf.carrier if leaf is not None else None

        rest_carrier: Bound[RestCarrier]
        if (
            leaf is not None
            and leaf.written_size.value == request.written_value
            and leaf.written_size.count == 1
            and isinstance(carrier, RestCarrier)
        ):
            # replace the existing rest on the carrier
            rest: Rest | None = carrier.rest
            if rest is not None:
                buffer.incorporate(item=DeleteRestRequest(target=rest))

            rest_carrier = carrier
        else:
            rest_carrier = ResultRef[RestCarrier]()
            buffer.incorporate(
                item=CreateRestCarrierRequest(
                    scope=scope,
                    measure=request.measure,
                    position=request.position,
                    written_value=request.written_value,
                    out=rest_carrier,
                ),
            )

        buffer.incorporate(
            item=CreateRestAction(
                rest_carrier=rest_carrier,
                staff=request.staff,
                out=request.out,
            ),
        )

        return buffer


class DeleteRestAnalyzer:
    """Decides direct deletion of a rest because it owns no child entities."""

    def analyze(
        self,
        *,
        request: DeleteRestRequest,
        resolver: ResolveBound,
    ) -> EmitBuffer:
        buffer: EmitBuffer = EmitBuffer(request=request)
        rest: Rest = request.target

        buffer.incorporate(item=DeleteRestAction(target=rest))

        return buffer
