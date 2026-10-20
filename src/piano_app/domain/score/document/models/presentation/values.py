from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True, kw_only=True)
class VerticalOffset:
    """A relation, never a distance: a factor of the automatic size (1 = as automatic) for a
    target the capabilities mark as scaled, else a fraction of the height of the target's
    frame, in either case measured by the renderer."""

    value: float = 0

    def __post_init__(self) -> None:
        if not isfinite(self.value):
            raise ValueError("Vertical offset must be finite.")


@dataclass(frozen=True, slots=True, kw_only=True)
class EndpointOffsets:
    """The same relation as ``VerticalOffset`` for the left and the right end."""

    left: float = 0
    right: float = 0

    def __post_init__(self) -> None:
        if not isfinite(self.left) or not isfinite(self.right):
            raise ValueError("Endpoint offsets must be finite.")


@dataclass(frozen=True, slots=True, kw_only=True)
class HorizontalOffset:
    """A place across the frame as a fraction of its width, measured by the renderer."""

    value: float = 0

    def __post_init__(self) -> None:
        if not isfinite(self.value):
            raise ValueError("Horizontal offset must be finite.")


@dataclass(frozen=True, slots=True, kw_only=True)
class HorizontalEndpointOffsets:
    """The places of the two ends across the frame, each a fraction of its width."""

    left: float = 0
    right: float = 0

    def __post_init__(self) -> None:
        if not isfinite(self.left) or not isfinite(self.right):
            raise ValueError("Horizontal endpoint offsets must be finite.")
