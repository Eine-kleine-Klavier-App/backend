from fractions import Fraction

from piano_app.domain.score.document.models.notation import RhythmicSize
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition, Voice
from piano_app.domain.score.document.models.structural.rhythm import (
    RhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.geometry import Point, Span, overflow
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError

# The room a new rhythmic item takes in its scope, read on the live document. A leaf is
# placed in the scope its request names; an item placed from its voice — its spans, the
# frames they clear, a new group — takes the deepest scope holding its start. Both are
# refused when they do not fit there. Neither function yields, so no geometric snapshot
# outlives the moment it is read.


def find_met_containers(
    *,
    geometry: ScoreGeometry,
    scope: RhythmicContainerParent,
    measure: Measure,
    position: MeasurePosition,
    size: RhythmicSize,
) -> list[RhythmicContainer]:
    """The containers of ``scope`` a new container of ``size`` starting at ``position``
    would meet.

    A container that does not fit in its scope is refused — the scope is given, never
    descended into, so the refusal is the container's own invariant. Only the met
    containers themselves are returned, never their geometry.
    """
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

    return [meeting.region for meeting in geometry.intersecting(span=placement, scope=scope)]


def locate_item(
    *,
    geometry: ScoreGeometry,
    voice: Voice,
    measure: Measure,
    position: MeasurePosition,
    written_length: Fraction,
) -> tuple[RhythmicContainerParent, Span]:
    """The scope of a new item of ``written_length`` starting at ``position`` in
    ``measure``, and its span written in that scope's own frame.

    The scope is the innermost one of ``voice`` holding the start (half-open: a start on
    a group's first instant is inside it). The item must fit in its scope, and a group and
    a voice are held to the same rule: an item may not tear out of its group, nor run past
    the last measure of its voice.
    """
    # a start outside its own measure is a wrong address, not a point further along: it
    # would silently land in the next measure, or off the end of the timeline
    if not measure.holds(position=position):
        raise MutationRejectedError("Position lies at or past the end of the measure.")

    start: Point = Point(
        frame=geometry.of_measure(measure=measure),
        value=position.value,
    ).to(frame=geometry.root)

    scope: RhythmicContainerParent
    local: Point
    scope, local = geometry.deepest_scope_at(point=start, voice=voice)
    span: Span = Span(frame=local.frame, start=local.value, length=written_length)

    # a group ends with its written interior, the timeline with the last measure
    if overflow(span=span) > 0:
        raise MutationRejectedError("Item does not fit in its scope.")

    return scope, span
