from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.rhythmic.room import (
    make_room,
)
from piano_app.domain.score.document.services.mutation.engine.buffer import EmitBuffer
from piano_app.domain.score.document.services.mutation.engine.resolver import ResolveBound
from piano_app.domain.score.document.services.mutation.instructions import (
    Bound,
    MutationRejectedError,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.rhythmic import (
    CreateRhythmicGroupAction,
    DeleteRhythmicGroupAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    CreateRhythmicGroupRequest,
    DeleteLeafRequest,
    DeleteRhythmicGroupRequest,
)


class CreateRhythmicGroupAnalyzer:
    """Decides placement and displacement for a new, empty rhythmic group.

    Placed exactly like a leaf: into the scope the request names, refused when it does
    not fit there, displacing the containers of that scope it meets. Its interior is
    left empty — the fill postprocessor tiles it with rests at the gesture boundary.
    """

    def analyze(
        self,
        *,
        request: CreateRhythmicGroupRequest,
        resolver: ResolveBound,
    ) -> EmitBuffer:
        buffer: EmitBuffer = EmitBuffer(request=request)
        # the scope may be a group created earlier in the same gesture
        scope: RhythmicContainerParent = resolver(request.scope)

        # mirrors the group's own guard: a group that scales nothing is refused, not a crash
        if request.written_size.fraction == request.occupied_size.fraction:
            raise MutationRejectedError("A group must differ in written and occupied size.")

        anchor: Bound[TemporalAnchor] = make_room(
            buffer=buffer,
            scope=scope,
            measure=request.measure,
            position=request.position,
            size=request.occupied_size,
        )

        buffer.incorporate(
            item=CreateRhythmicGroupAction(
                parent=scope,
                anchor=anchor,
                written_size=request.written_size,
                occupied_size=request.occupied_size,
                out=request.out,
            ),
        )

        return buffer


class DeleteRhythmicGroupAnalyzer:
    """Decides the rhythmic group's deletion cascade.

    Every direct leaf and subgroup triggers its own deletion before the group.
    """

    def analyze(
        self,
        *,
        request: DeleteRhythmicGroupRequest,
        resolver: ResolveBound,
    ) -> EmitBuffer:
        buffer: EmitBuffer = EmitBuffer(request=request)
        group: GroupRhythmicContainer = request.target

        for child in group.children:
            if isinstance(child, LeafRhythmicContainer):
                buffer.incorporate(item=DeleteLeafRequest(target=child))
            elif isinstance(child, GroupRhythmicContainer):
                buffer.incorporate(item=DeleteRhythmicGroupRequest(target=child))
            else:
                raise ValueError(f"Unknown container type: {type(child)}")

        buffer.incorporate(item=DeleteRhythmicGroupAction(target=group))

        return buffer
