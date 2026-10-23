from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations

from piano_app.domain.score.document.models.context import Context, Refrain, Volta
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry

from .index import ContextIndex
from .scope import Scope


@dataclass(frozen=True, slots=True, kw_only=True)
class Piece:
    """A stretch of the global timeline that belongs to one part of a repeat or a volta."""

    start: Fraction
    end: Fraction


def _holds(*, outer: Piece, inner: Piece) -> bool:
    return outer.start <= inner.start and inner.end <= outer.end


def check_nesting(*, elements: Sequence[Sequence[Piece]]) -> None:
    """Repeats and voltas may lie one inside another or apart, touching included; they may
    not lie partly over each other.

    An element is given by its pieces, in order and meeting end to start: a refrain has one,
    a volta its body and each of its fragments. One lies inside another when all of it lies
    in a single piece of the other, so a repeat may stand inside a fragment of a volta but
    not across the boundary between two of its pieces. Two elements over exactly the same
    bars, from the start of the first piece to the end of the last, are refused whatever they
    are: nothing tells which is inside, and a refrain over the very bars of a volta would
    never be played."""
    for first, second in combinations(elements, 2):
        first_extent: Piece = Piece(start=first[0].start, end=first[-1].end)
        second_extent: Piece = Piece(start=second[0].start, end=second[-1].end)
        if first_extent.end <= second_extent.start or second_extent.end <= first_extent.start:
            continue

        if first_extent == second_extent:
            raise ValueError(
                "Two repeats may not lie over exactly the same bars: nothing tells which is inside."
            )

        if any(_holds(outer=piece, inner=second_extent) for piece in first):
            continue

        if any(_holds(outer=piece, inner=first_extent) for piece in second):
            continue

        raise ValueError(
            "A repeat may lie inside one part of another or apart from it, "
            "not across its parts or partly over it."
        )


def _place(*, geometry: ScoreGeometry, anchor: TemporalAnchor | None) -> Fraction:
    return geometry.root.extent if anchor is None else geometry.point_of(anchor=anchor).value


def pieces_of_refrain(*, geometry: ScoreGeometry, refrain: Refrain) -> list[Piece]:
    return [
        Piece(
            start=_place(geometry=geometry, anchor=refrain.start),
            end=_place(geometry=geometry, anchor=refrain.end),
        )
    ]


def pieces_of_volta(*, geometry: ScoreGeometry, volta: Volta) -> list[Piece]:
    pieces: list[Piece] = [
        Piece(
            start=_place(geometry=geometry, anchor=volta.start),
            end=_place(geometry=geometry, anchor=volta.body_end),
        )
    ]
    for fragment in volta.fragments:
        pieces.append(
            Piece(
                start=_place(geometry=geometry, anchor=fragment.start),
                end=_place(geometry=geometry, anchor=fragment.end),
            )
        )

    return pieces


def pieces_of_elements(
    *,
    geometry: ScoreGeometry,
    contexts: ContextIndex,
    without: Context | None = None,
) -> list[list[Piece]]:
    """The pieces of every repeat and volta of the score, but ``without``: the one a change is
    being planned for, which is checked as it will be, not as it is."""
    return [
        *(
            pieces_of_refrain(geometry=geometry, refrain=refrain)
            for refrain in contexts.contexts_of(kind=Refrain, scope=Scope.score())
            if refrain is not without
        ),
        *(
            pieces_of_volta(geometry=geometry, volta=volta)
            for volta in contexts.contexts_of(kind=Volta, scope=Scope.score())
            if volta is not without
        ),
    ]
