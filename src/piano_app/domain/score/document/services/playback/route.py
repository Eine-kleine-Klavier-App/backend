from collections.abc import Sequence
from dataclasses import dataclass, field
from fractions import Fraction

from piano_app.domain.score.document.models.context import JumpRule, Refrain, Volta
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.services.contexts import ContextIndex, Scope
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry

# The most jumps one route may take: a score whose jumps never let it reach the end is refused
# instead of looping for ever.
_MAX_JUMPS: int = 10_000


@dataclass(frozen=True, slots=True, kw_only=True)
class RouteSegment:
    """A stretch of the global timeline played in one go; both ends are whole-note coordinates
    of the score, as everywhere in the geometry."""

    start: Fraction
    end: Fraction


@dataclass(frozen=True, slots=True, kw_only=True)
class _Rule:
    """A jump placed on the global timeline, and the arrivals at its source it is taken on."""

    source: Fraction
    target: Fraction
    arrivals: frozenset[int]


@dataclass(slots=True, kw_only=True)
class _Element:
    """The jumps of one repeat or volta, the place its start lies at, the last place its jumps
    leave from and how many times each of the places its jumps leave from has been reached
    since the element was last entered."""

    head: Fraction
    end: Fraction
    rules: list[_Rule]
    reached: dict[Fraction, int] = field(default_factory=dict)


def _play(*, route: list[RouteSegment], start: Fraction, end: Fraction) -> None:
    """Append a stretch to the route, joined to the last one when they meet."""
    if start >= end:
        return

    if route and route[-1].end == start:
        route[-1] = RouteSegment(start=route[-1].start, end=end)
        return

    route.append(RouteSegment(start=start, end=end))


def _element_of(
    *,
    geometry: ScoreGeometry,
    head: TemporalAnchor,
    rules: Sequence[JumpRule],
) -> _Element:
    """The element with its jumps on the timeline; no barline stands for the end of the score."""
    extent: Fraction = geometry.root.extent

    def place(anchor: TemporalAnchor | None) -> Fraction:
        return extent if anchor is None else geometry.point_of(anchor=anchor).value

    placed: list[_Rule] = [
        _Rule(
            source=place(rule.jump.source),
            target=place(rule.jump.target),
            arrivals=rule.arrivals,
        )
        for rule in rules
    ]
    return _Element(
        head=place(head),
        end=max(rule.source for rule in placed),
        rules=placed,
    )


def _arrive(*, elements: Sequence[_Element], at: Fraction) -> tuple[_Element, _Rule] | None:
    """The jump taken on reaching ``at`` after playing what ends there, if any.

    The elements are asked one after the other, the innermost first. An element that has
    jumps leaving from ``at`` counts this arrival, and takes the first of them whose arrivals
    hold the count; one that takes none leaves the arrival to the next. An element that
    jumped away does not hand the arrival on, so an outer one counts only the arrivals the
    inner ones let through."""
    for element in elements:
        here: list[_Rule] = [rule for rule in element.rules if rule.source == at]
        if not here:
            continue

        count: int = element.reached.get(at, 0) + 1
        element.reached[at] = count
        for rule in here:
            if count in rule.arrivals:
                return element, rule

    return None


def build_route(*, geometry: ScoreGeometry, contexts: ContextIndex) -> list[RouteSegment]:
    """The order the score is played in, from its jumps: a list of stretches of the global
    timeline, each played right after the one before it.

    The score is played from its start up to the next barline a jump leaves from, or up to
    its end. Reaching that barline is an arrival, and the elements (repeats and voltas) that
    have jumps there decide whether one is taken (see ``_arrive``); landing at a barline is
    not reaching it, so a jump that lands where another leaves from does not trigger it.
    The count of arrivals of an element starts afresh whenever its start is reached from
    outside it: by playing on into it, or by a jump that leaves from a place beyond its last
    jump. A jump that leaves from inside it, its own or that of an element lying in it, does
    not start the count afresh, which makes an element inside another play as it is written
    every time it is entered. A jump that leaves from the end of the score is taken when the
    end is reached, one that lands there ends the route.
    """
    elements: list[_Element] = [
        _element_of(geometry=geometry, head=refrain.start, rules=refrain.rules)
        for refrain in contexts.contexts_of(kind=Refrain, scope=Scope.score())
    ] + [
        _element_of(geometry=geometry, head=volta.start, rules=volta.rules)
        for volta in contexts.contexts_of(kind=Volta, scope=Scope.score())
    ]
    # the innermost first: the one that starts later, at the same start the one that ends
    # sooner (two never lie over the same bars)
    elements.sort(key=lambda each: (-each.head, each.end))
    extent: Fraction = geometry.root.extent
    stops: list[Fraction] = sorted({rule.source for each in elements for rule in each.rules})

    route: list[RouteSegment] = []
    position: Fraction = Fraction(0)
    landed_from: Fraction | None = None
    taken: int = 0
    while position < extent:
        stop: Fraction = next((each for each in stops if each > position), extent)
        for element in elements:
            entered_from_inside: bool = (
                landed_from is not None
                and element.head == position
                and element.head < landed_from <= element.end
            )
            if position <= element.head < stop and not entered_from_inside:
                element.reached.clear()

        _play(route=route, start=position, end=stop)
        position = stop
        landed_from = None

        jump: tuple[_Element, _Rule] | None = _arrive(elements=elements, at=stop)
        if jump is not None:
            taken += 1
            if taken > _MAX_JUMPS:
                raise ValueError("The jumps of the score never let it reach its end.")

            landed_from = stop
            position = jump[1].target

    return route
