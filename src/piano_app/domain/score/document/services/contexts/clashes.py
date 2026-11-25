from dataclasses import dataclass
from enum import Enum, auto
from fractions import Fraction

from piano_app.domain.score.document.models.context import (
    ClefChange,
    Context,
    DynamicChange,
    Hairpin,
    KeySignatureChange,
    OctaveTransposition,
    Slur,
    SpanContext,
    StaffScoped,
    SustainHold,
    TempoChange,
    TempoTransition,
    VoiceScoped,
)
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    Staff,
    Voice,
)
from piano_app.domain.score.document.services.geometry import Piece, Point
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry

from .index import ContextIndex
from .scope import Scope

_SAME_PLACE_REASON: str = "Another context of the same kind already starts there."


class ClashKind(Enum):
    """How a placement meets a context it may not share the timeline with."""

    SAME_PLACE = auto()
    OVERLAP = auto()
    INSIDE = auto()
    HOLDS = auto()


class OnSamePlace(Enum):
    """What creating a context does to one of its kind already starting at the same place."""

    REPLACE = auto()
    NOTHING = auto()


@dataclass(frozen=True, slots=True, kw_only=True)
class Clash:
    """One context a placement meets, how, and why that is refused."""

    kind: ClashKind
    context: Context
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class KindPolicy:
    """What is not decided by a kind's model type: what a creation does at a place already
    taken, whether its spans may overlap, and which partner kind may not lie strictly inside
    it (a point inside a span of the partner kind, or a partner point inside the span).

    Whether a kind is a point or a span, and what it is scoped to, follow from its type.
    """

    on_same_place: OnSamePlace
    may_overlap: bool = False
    partner: type[Context] | None = None


# A new kind of context is added here.
_POLICIES: dict[type[Context], KindPolicy] = {
    ClefChange: KindPolicy(on_same_place=OnSamePlace.REPLACE),
    KeySignatureChange: KindPolicy(on_same_place=OnSamePlace.REPLACE),
    TempoChange: KindPolicy(on_same_place=OnSamePlace.REPLACE, partner=TempoTransition),
    DynamicChange: KindPolicy(on_same_place=OnSamePlace.REPLACE, partner=Hairpin),
    OctaveTransposition: KindPolicy(on_same_place=OnSamePlace.NOTHING),
    Hairpin: KindPolicy(on_same_place=OnSamePlace.NOTHING, partner=DynamicChange),
    TempoTransition: KindPolicy(on_same_place=OnSamePlace.NOTHING, partner=TempoChange),
    Slur: KindPolicy(on_same_place=OnSamePlace.NOTHING, may_overlap=True),
    SustainHold: KindPolicy(on_same_place=OnSamePlace.NOTHING),
}


def policy_of(*, kind: type[Context]) -> KindPolicy | None:
    """The policy of a kind of context, or None for a kind that has none."""
    return _POLICIES.get(kind)


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


def find_clashes(
    *,
    contexts: ContextIndex,
    kind: type[Context],
    start: Fraction,
    end: Fraction | None,
    staff: Staff | None,
    voice: Voice | None,
    ignore: Context | None = None,
) -> list[Clash]:
    """The contexts a context of ``kind`` may not share the timeline with if it were placed at
    ``start`` — a span if ``end`` is given, else a point — and how each meets it. Positions are
    on the global timeline; ``staff`` and ``voice`` are what the kind is scoped to, the one
    that applies being read. ``ignore`` is the context being moved. A kind without a policy
    meets nothing.

    It decides nothing: whoever places the context decides what to do with each clash.
    """
    policy: KindPolicy | None = _POLICIES.get(kind)
    if policy is None:
        return []

    scope: Scope
    if issubclass(kind, StaffScoped):
        if staff is None:
            return []

        scope = Scope.of_staff(staff=staff)
    elif issubclass(kind, VoiceScoped):
        if voice is None:
            return []

        scope = Scope.of_voice(voice=voice)
    else:
        scope = Scope.score()

    clashes: list[Clash] = []

    if end is None:
        for same in contexts.starting_at(kind=kind, point=start, scope=scope):
            if same is not ignore:
                clashes.append(
                    Clash(kind=ClashKind.SAME_PLACE, context=same, reason=_SAME_PLACE_REASON)
                )

        if policy.partner is not None and issubclass(policy.partner, SpanContext) and start > 0:
            right: Piece[SpanContext | None, SpanContext] = contexts.piece_at(
                kind=policy.partner, point=start, scope=scope
            )
            left: Piece[SpanContext | None, SpanContext] = contexts.pieces_over(
                kind=policy.partner, start=Fraction(0), end=start, scope=scope
            )[-1]
            # a span that lies over the point on both sides begins before it and ends after
            for across in right.sources:
                if across in left.sources:
                    clashes.append(
                        Clash(
                            kind=ClashKind.INSIDE,
                            context=across,
                            reason=(
                                f"A {kind.__name__} cannot be placed inside a "
                                f"{policy.partner.__name__}."
                            ),
                        )
                    )

        return clashes

    if not issubclass(kind, SpanContext):
        raise TypeError(f"{kind.__name__} is not a span: it has no end.")

    if not policy.may_overlap:
        listed: set[Context] = set()
        for piece in contexts.pieces_over(kind=kind, start=start, end=end, scope=scope):
            for overlapping in piece.sources:
                if overlapping is not ignore and overlapping not in listed:
                    listed.add(overlapping)
                    clashes.append(
                        Clash(
                            kind=ClashKind.OVERLAP,
                            context=overlapping,
                            reason=f"A {kind.__name__} cannot overlap another.",
                        )
                    )

    if policy.partner is not None:
        # the first piece begins at ``start``; each later one begins where a point starts
        for cut in contexts.pieces_over(kind=policy.partner, start=start, end=end, scope=scope)[1:]:
            inside: Context | None = cut.value
            if inside is not None:
                clashes.append(
                    Clash(
                        kind=ClashKind.HOLDS,
                        context=inside,
                        reason=(
                            f"A {kind.__name__} cannot hold a {policy.partner.__name__} "
                            "strictly inside."
                        ),
                    )
                )

    return clashes
