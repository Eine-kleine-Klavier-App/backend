from dataclasses import dataclass
from enum import StrEnum


class StemDirection(StrEnum):
    UP = "up"
    DOWN = "down"


@dataclass(frozen=True, slots=True, kw_only=True)
class StemOverride:
    """How the user wants one stem drawn.

    ``length_percent`` scales the renderer's default stem length: 100 leaves it as it is,
    less shortens, more lengthens. The renderer owns what the default is, so the document
    never stores a length in drawing units.
    """

    direction: StemDirection
    length_percent: int = 100

    def __post_init__(self) -> None:
        if self.length_percent <= 0:
            raise ValueError("Stem length must be a positive percentage.")
