from dataclasses import dataclass

from piano_app.domain.score.document.models.structural.jump import Jump


@dataclass(frozen=True, slots=True, kw_only=True)
class JumpRule:
    """A jump and the arrivals at its source on which it is taken, counted from one: how an
    element built from jumps (a refrain, a volta) tells playback when to take each of them."""

    jump: Jump
    arrivals: frozenset[int]
