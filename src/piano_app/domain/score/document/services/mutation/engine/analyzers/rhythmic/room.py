from piano_app.domain.score.document.models.notation import RhythmicSize
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    TemporalAnchor,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.geometry import Point, Span, overflow
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import find_anchor_at
from piano_app.domain.score.document.services.mutation.engine.buffer import EmitBuffer
from piano_app.domain.score.document.services.mutation.instructions import (
    Bound,
    MutationRejectedError,
    ResultRef,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    DeleteLeafRequest,
    DeleteRhythmicGroupRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.temporal import (
    CreateTemporalAnchorRequest,
)

# The room a new rhythmic container takes in its scope — the same for a leaf and a
# group, since both are a span in the scope that starts at an anchor.


def make_room(
    *,
    buffer: EmitBuffer,
    scope: RhythmicContainerParent,
    measure: Measure,
    position: MeasurePosition,
    size: RhythmicSize,
) -> Bound[TemporalAnchor]:
    """Clears the room for a container of ``size`` starting at ``position`` in ``scope``
    and returns its anchor.

    The anchor is reused or requested; every container of the scope the new one meets is
    deleted before it. A container that does not fit in its scope is refused — the scope
    is given, never descended into, so the refusal is the container's own invariant.
    """
    existing_anchor: TemporalAnchor | None = find_anchor_at(measure=measure, position=position)

    anchor: Bound[TemporalAnchor]
    if existing_anchor is not None:
        anchor = existing_anchor
    else:
        anchor = ResultRef[TemporalAnchor]()
        buffer.incorporate(
            item=CreateTemporalAnchorRequest(
                measure=measure,
                position=position,
                out=anchor,
            )
        )

    geometry: ScoreGeometry = ScoreGeometry(origin=measure)

    # the point is restated in the scope's own frame; the size stays as written, since a
    # size means the value written in the scope it lands in
    local: Point = Point(
        frame=geometry.of_measure(measure=measure),
        value=position.value,
    ).to(frame=geometry.of_scope(scope=scope))
    placement: Span = Span(frame=local.frame, start=local.value, length=size.fraction)

    # geometry only reports how far the container outgrows its scope — refusing it is the
    # analyzer's own invariant, and it belongs here rather than down in the geometry
    if overflow(span=placement) > 0:
        raise MutationRejectedError("Container does not fit in its scope.")

    to_remove: list[RhythmicContainer] = [
        meeting.region for meeting in geometry.intersecting(span=placement, scope=scope)
    ]

    for item in to_remove:
        if isinstance(item, LeafRhythmicContainer):
            buffer.incorporate(item=DeleteLeafRequest(target=item))
        elif isinstance(item, GroupRhythmicContainer):
            buffer.incorporate(item=DeleteRhythmicGroupRequest(target=item))
        else:
            raise ValueError(f"Unknown container type: {type(item)}")

    return anchor
