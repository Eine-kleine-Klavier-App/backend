from dataclasses import dataclass
from fractions import Fraction

import pytest

from piano_app.domain.score.document.services.geometry import Frame, Transform


@dataclass(frozen=True, slots=True, kw_only=True)
class StubFrame:
    """A coordinate space with no model behind it.

    The core is supposed to work on frames alone, so its tests deliberately never
    build a score — if these ever need one, the decoupling has been lost.
    """

    name: str
    parent: Frame | None
    to_parent: Transform
    extent: Fraction


@pytest.fixture
def root() -> StubFrame:
    """A timeline four whole notes long — the root has a size like every other frame."""
    return StubFrame(
        name="timeline",
        parent=None,
        to_parent=Transform.identity(),
        extent=Fraction(4),
    )


@pytest.fixture
def measure(root: StubFrame) -> StubFrame:
    """A 4/4 bar starting one whole note in: shifted, never compressed."""
    return StubFrame(
        name="measure",
        parent=root,
        to_parent=Transform.of_shift(offset=Fraction(1)),
        extent=Fraction(1),
    )


@pytest.fixture
def triplet(root: StubFrame) -> StubFrame:
    """Three written eighths squeezed into a quarter, starting at 1/4."""
    return StubFrame(
        name="triplet",
        parent=root,
        to_parent=Transform.of_nesting(
            written=Fraction(3, 8),
            occupied=Fraction(1, 4),
            offset=Fraction(1, 4),
        ),
        extent=Fraction(3, 8),
    )
