from dataclasses import dataclass

from piano_app.domain.score.document.services.geometry import Span

from .transform import PitchTransform


@dataclass(frozen=True, slots=True, kw_only=True)
class PitchRegion:
    """A numeric pitch rule in a half-open temporal region."""

    span: Span
    transform: PitchTransform


@dataclass(frozen=True, slots=True, kw_only=True)
class OctaveRegion:
    """An additive octave shift in a half-open temporal region."""

    span: Span
    octaves: int
