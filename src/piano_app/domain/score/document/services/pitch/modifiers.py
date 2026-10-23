from enum import Enum, auto

from piano_app.domain.score.document.models.context import (
    ClefChange,
    Context,
    KeySignatureChange,
    OctaveTransposition,
)
from piano_app.domain.score.document.services.geometry import Piece


class Composition(Enum):
    """How the contexts of one kind that are in force together make one answer.

    An accidental carried by staff step to the barline is a third way, but it is read from
    the notes of the measure, not from a kind of context (``ScorePitch.accidental_at``).
    """

    # the last one that began governs: a clef, a key signature
    EXCLUSIVE = auto()
    # every one in force counts, their shifts sum: an octave line
    ADDITIVE = auto()


# What changes what a staff step sounds like, and how its contexts compose. A new modifier of
# pitch is registered here.
MODIFIERS: dict[type[Context], Composition] = {
    ClefChange: Composition.EXCLUSIVE,
    KeySignatureChange: Composition.EXCLUSIVE,
    OctaveTransposition: Composition.ADDITIVE,
}


def in_force[T: Context](*, kind: type[T], piece: Piece[T | None, T]) -> tuple[T, ...]:
    """The contexts of a registered kind that count on a piece: the one that governs for an
    exclusive kind, all that cover it for an additive one."""
    composition: Composition = MODIFIERS[kind]
    if composition is Composition.EXCLUSIVE:
        return () if piece.value is None else (piece.value,)

    return piece.sources
