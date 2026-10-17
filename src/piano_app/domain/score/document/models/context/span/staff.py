from dataclasses import dataclass
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink

from ..scope import StaffScoped
from .base import SpanContext

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.structural import Staff, TemporalAnchor


@dataclass(kw_only=True, eq=False)
class OctaveTransposition(StaffScoped, SpanContext):
    """How far the written notes in this span sound transposed — an 8va/15va
    bracket. ``octaves`` is signed: positive sounds higher than written."""

    _octaves: int

    @property
    def octaves(self) -> int:
        return self._octaves

    def _check_invariants(self) -> None:
        super()._check_invariants()

        if not 1 <= abs(self._octaves) <= 2:
            raise ValueError("Octave transposition must be 1 or 2 octaves (8va/15va), up or down.")

    @classmethod
    def create(
        cls,
        *,
        start: TemporalAnchor,
        end: TemporalAnchor,
        staff: Staff,
        octaves: int,
        sink: MutationSink = DIRECT_SINK,
    ) -> OctaveTransposition:
        octave_transposition = cls(
            _start=start,
            _end=end,
            _staff=staff,
            _octaves=octaves,
        )

        octave_transposition.attach(sink=sink)
        return octave_transposition

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        start: TemporalAnchor,
        end: TemporalAnchor,
        staff: Staff,
        octaves: int,
        sink: MutationSink = DIRECT_SINK,
    ) -> OctaveTransposition:
        octave_transposition = cls(
            id=id,
            _start=start,
            _end=end,
            _staff=staff,
            _octaves=octaves,
        )

        octave_transposition.attach(sink=sink)
        return octave_transposition
