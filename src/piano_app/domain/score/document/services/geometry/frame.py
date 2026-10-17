from fractions import Fraction
from typing import Protocol

from .errors import UnreachableFrameError
from .transform import Transform


class Frame(Protocol):
    """A coordinate space — a tuplet group, a measure, or the score's whole timeline.

    Frames form a tree rooted at the single global timeline. A frame knows only its
    parent and the affine step into it; it knows nothing about what the space means
    musically and nothing about the model type backing it. A metric leaf is NOT a
    frame — it has no interior, it is merely placed inside one.
    """

    @property
    def parent(self) -> Frame | None:
        """The enclosing space, or ``None`` for the root."""
        ...

    @property
    def to_parent(self) -> Transform:
        """The step into ``parent``. Unused on the root."""
        ...

    @property
    def extent(self) -> Fraction:
        """How far the space reaches in its own units. Every space is bounded: even the
        whole timeline ends — where the score's measures do."""
        ...


def to_root(*, frame: Frame) -> tuple[Transform, Frame]:
    """Collapse the whole chain above ``frame`` into one transform, and report the
    root it lands in (so two frames can be checked for belonging together)."""
    transform: Transform = Transform.identity()

    current: Frame = frame
    while current.parent is not None:
        transform = transform.then(current.to_parent)
        current = current.parent

    return transform, current


def conversion(*, source: Frame, target: Frame) -> Transform:
    """The single affine step from ``source`` coordinates into ``target`` ones.

    Up to the shared root, then back down by the inverse — so any pair of frames
    converts directly, including two unrelated tuplets or a group and a measure.
    """
    source_transform, source_root = to_root(frame=source)
    target_transform, target_root = to_root(frame=target)

    # frames compare by what they stand for, not by object identity: adapters over
    # the live model are built on demand, so the same space is many short-lived
    # objects
    if source_root != target_root:
        raise UnreachableFrameError("Frames belong to different roots.")

    return source_transform.then(target_transform.inverse())
