from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Carrier
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import iter_leaves

from .route import RouteSegment
from .timeline import Timeline

# Inside a gradual change of tempo the time is not in proportion to the position, so the moments
# there are taken at every step of this many whole notes.
_CURVE_STEP: Fraction = Fraction(1, 128)


@dataclass(frozen=True, slots=True, kw_only=True)
class PlayedAnchor:
    """One leaf of the score (a note, a chord or a rest) as it is played: its carrier and when
    it starts and stops, in milliseconds. A leaf in a repeated part has one for each pass."""

    carrier_id: str
    start_ms: float
    end_ms: float


@dataclass(frozen=True, slots=True, kw_only=True)
class Moment:
    """A place of the score and the time at which the playback is there."""

    position: Fraction
    time_ms: float


@dataclass(frozen=True, slots=True, kw_only=True)
class TimelineSegment:
    """One stretch of the route, played in one go: the places of the score it covers, the
    times it takes, and moments in between (ends included) from which the time of any place in
    it is read by interpolation. A repeated part is a segment for each pass."""

    start: Fraction
    end: Fraction
    start_ms: float
    end_ms: float
    moments: tuple[Moment, ...]


def build_anchors(
    *,
    document: ScoreDocument,
    geometry: ScoreGeometry,
    route: Sequence[RouteSegment],
    timeline: Timeline,
) -> list[PlayedAnchor]:
    """The leaves of the score as they are played, in the order they start. A leaf belongs to
    the stretch of the route it starts in and is cut at its end, as in ``build_sounds``."""
    anchors: list[PlayedAnchor] = []
    offset: Fraction = Fraction(0)
    for segment in route:
        for voice in document.voices:
            for leaf in iter_leaves(voice):
                carrier: Carrier | None = leaf.carrier
                span = geometry.global_span_of(container=leaf)
                if carrier is None or not segment.start <= span.start < segment.end:
                    continue

                anchors.append(
                    PlayedAnchor(
                        carrier_id=carrier.id,
                        start_ms=timeline.ms_at(position=offset + span.start - segment.start),
                        end_ms=timeline.ms_at(
                            position=offset + min(span.end, segment.end) - segment.start
                        ),
                    )
                )

        offset += segment.end - segment.start

    anchors.sort(key=lambda anchor: anchor.start_ms)

    return anchors


def build_segments(
    *,
    document: ScoreDocument,
    geometry: ScoreGeometry,
    route: Sequence[RouteSegment],
    timeline: Timeline,
) -> list[TimelineSegment]:
    """The map from a place of the score to the time of the playback, a segment for each
    stretch of the route. The moments are at the edges of the leaves, at the starts of the
    measures, where the speed of the tempo changes, and densely inside a gradual change."""
    edges: set[Fraction] = set()
    for voice in document.voices:
        for leaf in iter_leaves(voice):
            span = geometry.global_span_of(container=leaf)
            edges.add(span.start)
            edges.add(span.end)

    for measure in document.measures:
        edges.add(geometry.measure_span(measure=measure).start)

    segments: list[TimelineSegment] = []
    offset: Fraction = Fraction(0)
    for route_segment in route:
        length: Fraction = route_segment.end - route_segment.start
        places: set[Fraction] = {route_segment.start, route_segment.end}
        for edge in edges:
            if route_segment.start < edge < route_segment.end:
                places.add(edge)

        for region in timeline.regions:
            if not offset <= region.start < offset + length:
                continue

            places.add(route_segment.start + region.start - offset)
            if region.start_value != region.end_value:
                at: Fraction = region.start + _CURVE_STEP
                while at < region.end:
                    places.add(route_segment.start + at - offset)
                    at += _CURVE_STEP

        moments: list[Moment] = []
        for place in sorted(places):
            moments.append(
                Moment(
                    position=place,
                    time_ms=timeline.ms_at(position=offset + place - route_segment.start),
                )
            )

        segments.append(
            TimelineSegment(
                start=route_segment.start,
                end=route_segment.end,
                start_ms=moments[0].time_ms,
                end_ms=moments[-1].time_ms,
                moments=tuple(moments),
            )
        )
        offset += length

    return segments
