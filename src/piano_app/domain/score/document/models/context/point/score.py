from dataclasses import dataclass
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.score.document.models.notation import DottedRhythmicValue, TempoMarking

from .base import PointContext

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.structural import TemporalAnchor


@dataclass(kw_only=True, eq=False)
class TempoChange(PointContext):
    """A tempo assertion: ``bpm`` beats of ``beat`` per minute.

    The optional word is derived from the numeric tempo, normalized to quarter notes.
    Score-scoped — no scope mixin, extends PointContext directly.
    """

    _beat: DottedRhythmicValue
    _bpm: int
    _show_label: bool = False

    @property
    def beat(self) -> DottedRhythmicValue:
        return self._beat

    @property
    def bpm(self) -> int:
        return self._bpm

    @property
    def label(self) -> TempoMarking | None:
        return (
            TempoMarking.for_bpm(quarter_bpm=self.beat.fraction * 4 * self.bpm)
            if self.show_label
            else None
        )

    @property
    def show_label(self) -> bool:
        return self._show_label

    def _check_invariants(self) -> None:
        super()._check_invariants()

        if self._bpm < 1:
            raise ValueError("Tempo must be at least 1 beat per minute.")

    @classmethod
    def create(
        cls,
        *,
        start: TemporalAnchor,
        beat: DottedRhythmicValue,
        bpm: int,
        show_label: bool = False,
        sink: MutationSink = DIRECT_SINK,
    ) -> TempoChange:
        tempo_change = cls(_start=start, _beat=beat, _bpm=bpm, _show_label=show_label)

        tempo_change.attach(sink=sink)
        return tempo_change

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        start: TemporalAnchor,
        beat: DottedRhythmicValue,
        bpm: int,
        show_label: bool = False,
        sink: MutationSink = DIRECT_SINK,
    ) -> TempoChange:
        tempo_change = cls(id=id, _start=start, _beat=beat, _bpm=bpm, _show_label=show_label)

        tempo_change.attach(sink=sink)
        return tempo_change
