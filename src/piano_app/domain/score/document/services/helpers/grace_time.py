from fractions import Fraction

from piano_app.domain.score.document.models.notation import GraceType
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceGroup,
    LeafRhythmicContainer,
)

# A grace note borrows time from the note it is attached to (owner, 2026-11-06, ``grace-notes``):
# without a slash it sounds as written, with a slash a quarter of that.
SLASHED_SCALE: Fraction = Fraction(1, 4)


def sounding_of(*, group: GraceGroup, written: Fraction) -> Fraction:
    """How long a grace note of the group written as ``written`` sounds."""
    return written * SLASHED_SCALE if group.grace_type is GraceType.ACCIACCATURA else written


def taken_from(*, leaf: LeafRhythmicContainer) -> Fraction:
    """The time the grace notes before and after the leaf's note take from it together."""
    total: Fraction = Fraction(0)
    for group in (leaf.grace_before, leaf.grace_after):
        if group is not None:
            for item in group.grace_items:
                total += sounding_of(group=group, written=item.rhythmic_value.fraction)

    return total


def fits(*, leaf: LeafRhythmicContainer, length: Fraction, extra: Fraction = Fraction(0)) -> bool:
    """Whether the grace notes of the leaf and ``extra`` more leave the note some of its
    ``length``: it cannot give all of it."""
    return taken_from(leaf=leaf) + extra < length
