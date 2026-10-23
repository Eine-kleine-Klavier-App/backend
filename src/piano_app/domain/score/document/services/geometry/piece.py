from dataclasses import dataclass

from .coordinates import Span


@dataclass(frozen=True, slots=True, kw_only=True)
class Piece[V, S = V]:
    """One stretch of an answer over a span, and what holds on it.

    An answer over an interval is an ordered list of pieces with no gaps and no overlaps that
    covers the queried interval exactly. It is cut at the boundary of every source and never
    merged by equal value, so no source is lost; a caller may merge, the reverse is
    impossible. An answer at a point is the one piece holding the point: half-open, so on a
    boundary the right piece wins, as in ``Span``.

    ``value`` is what the map answers with; ``sources`` are the things that produced the
    piece, in the order they started.
    """

    span: Span
    value: V
    sources: tuple[S, ...]
