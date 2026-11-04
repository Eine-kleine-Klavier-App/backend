from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from piano_app.domain.score.document.models.context import SustainHold
from piano_app.domain.score.document.services.contexts import ContextIndex, Scope
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry

from .route import RouteSegment


@dataclass(frozen=True, slots=True, kw_only=True)
class PedalSpan:
    """A stretch of the time of the route with the sustain pedal down."""

    start: Fraction
    end: Fraction


def build_pedal(
    *,
    route: Sequence[RouteSegment],
    geometry: ScoreGeometry,
    contexts: ContextIndex,
) -> list[PedalSpan]:
    """Where the sustain pedal is down along the route, in the time of the route.

    The pedal is down from where its span begins to where it ends, as long as the route goes
    straight on: a jump lifts it (owner, 2026-11-07), so the part of a span in each stretch of
    the route is a pedal of its own and a pedal does not stay down when a jump skips its end.
    """
    spans: list[PedalSpan] = []
    offset: Fraction = Fraction(0)
    for segment in route:
        for hold in contexts.contexts_of(kind=SustainHold, scope=Scope.score()):
            start: Fraction = max(geometry.point_of(anchor=hold.start).value, segment.start)
            end: Fraction = min(geometry.end_of(context=hold).value, segment.end)
            if start < end:
                spans.append(
                    PedalSpan(
                        start=offset + start - segment.start,
                        end=offset + end - segment.start,
                    )
                )

        offset += segment.end - segment.start

    return spans
