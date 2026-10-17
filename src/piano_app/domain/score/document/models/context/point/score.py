from dataclasses import dataclass
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.score.document.models.notation import TempoMarking

from .base import PointContext

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.structural import TemporalAnchor


@dataclass(kw_only=True, eq=False)
class TempoChange(PointContext):
    """A tempo assertion — a metronome mark, a word marking, or both.

    Both are optional individually (a score may show only "Allegro" with no BPM, or
    only "♩ = 120" with no word marking) but not both absent — that would assert
    nothing. Score-scoped — no scope mixin, extends PointContext directly.
    """

    _bpm: int | None = None
    _marking: TempoMarking | None = None

    @property
    def bpm(self) -> int | None:
        return self._bpm

    @property
    def marking(self) -> TempoMarking | None:
        return self._marking

    def _check_invariants(self) -> None:
        super()._check_invariants()

        if self._bpm is not None and self._bpm < 1:
            raise ValueError("Tempo must be at least 1 BPM.")

        if self._bpm is None and self._marking is None:
            raise ValueError("Tempo change must give a BPM, a marking, or both.")

    @classmethod
    def create(
        cls,
        *,
        start: TemporalAnchor,
        bpm: int | None = None,
        marking: TempoMarking | None = None,
        sink: MutationSink = DIRECT_SINK,
    ) -> TempoChange:
        tempo_change = cls(_start=start, _bpm=bpm, _marking=marking)

        tempo_change.attach(sink=sink)
        return tempo_change

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        start: TemporalAnchor,
        bpm: int | None = None,
        marking: TempoMarking | None = None,
        sink: MutationSink = DIRECT_SINK,
    ) -> TempoChange:
        tempo_change = cls(id=id, _start=start, _bpm=bpm, _marking=marking)

        tempo_change.attach(sink=sink)
        return tempo_change
