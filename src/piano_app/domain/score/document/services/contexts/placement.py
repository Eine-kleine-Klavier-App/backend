from collections.abc import Sequence
from fractions import Fraction

from piano_app.domain.score.document.models.context import (
    Context,
    DynamicChange,
    Hairpin,
    SpanContext,
    TempoChange,
    TempoTransition,
)
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    Voice,
)
from piano_app.domain.score.document.services.geometry import Point
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry

from .context_map import ContextMap

# the gradual change that a point of the key may not be placed inside, and the other way round
_SPAN_OF: dict[type[Context], type[SpanContext]] = {
    TempoChange: TempoTransition,
    DynamicChange: Hairpin,
}
_POINT_OF: dict[type[SpanContext], type[Context]] = {
    TempoTransition: TempoChange,
    Hairpin: DynamicChange,
}


def global_position(
    *,
    geometry: ScoreGeometry,
    measure: Measure,
    position: MeasurePosition,
) -> Fraction:
    """A measure position on the global timeline."""
    return (
        Point(frame=geometry.of_measure(measure=measure), value=position.value)
        .to(frame=geometry.root)
        .value
    )


def find_point_conflict(
    *,
    context_map: ContextMap,
    point_type: type[Context],
    at: Fraction,
    voices: Sequence[Voice] | None,
) -> str | None:
    """Why a point context of ``point_type`` may not be placed at ``at`` on the global
    timeline, or None. A tempo or dynamic may sit at the start or the end of a gradual change
    of its kind but not strictly inside one — for a dynamic, one that names its voices."""
    span_type: type[SpanContext] | None = _SPAN_OF.get(point_type)
    if span_type is None:
        return None

    if context_map.spans_across(span_type=span_type, start=at, end=at, voices=voices):
        return f"A {point_type.__name__} cannot be placed inside a {span_type.__name__}."

    return None


def find_span_conflict(
    *,
    context_map: ContextMap,
    span_type: type[SpanContext],
    start: Fraction,
    end: Fraction,
    voices: Sequence[Voice] | None,
    ignore: SpanContext | None = None,
) -> str | None:
    """Why a span of ``span_type`` may not cover the half-open ``[start, end)`` on the global
    timeline, or None. A hairpin or tempo transition may not overlap another of its kind
    that shares a voice, nor hold a point of its kind strictly inside."""
    point_type: type[Context] | None = _POINT_OF.get(span_type)
    if point_type is None:
        return None

    if context_map.spans_overlapping(
        span_type=span_type, start=start, end=end, voices=voices, ignore=ignore
    ):
        return f"A {span_type.__name__} cannot overlap another."

    if context_map.points_inside(
        point_type=point_type, start=start, end=end, voices=voices, ignore=None
    ):
        return f"A {span_type.__name__} cannot hold a {point_type.__name__} strictly inside."

    return None
