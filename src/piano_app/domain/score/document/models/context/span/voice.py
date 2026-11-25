from dataclasses import dataclass
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.score.document.models.notation import HairpinType

from ..scope import VoiceScoped
from .base import SpanContext

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.structural import TemporalAnchor, Voice


def _check_steps(*, steps: int) -> None:
    if steps == 0:
        raise ValueError("A hairpin must change the dynamic by at least one level.")


@dataclass(kw_only=True, eq=False)
class Hairpin(VoiceScoped, SpanContext):
    _steps: int

    @property
    def steps(self) -> int:
        """Dynamic levels from the level in force at the start to the end: above zero is a
        crescendo, below zero a diminuendo."""
        return self._steps

    @property
    def hairpin_type(self) -> HairpinType:
        return HairpinType.CRESCENDO if self._steps > 0 else HairpinType.DIMINUENDO

    def _check_invariants(self) -> None:
        super()._check_invariants()
        _check_steps(steps=self._steps)

    def set_steps(self, *, steps: int, sink: MutationSink = DIRECT_SINK) -> None:
        """Change by how many dynamic levels the hairpin moves, keeping the hairpin itself."""
        _check_steps(steps=steps)
        sink.set_field(self, "_steps", steps)

    @classmethod
    def create(
        cls,
        *,
        start: TemporalAnchor,
        end: TemporalAnchor | None,
        voice: Voice,
        steps: int,
        sink: MutationSink = DIRECT_SINK,
    ) -> Hairpin:
        hairpin = cls(
            _start=start,
            _end=end,
            _voice=voice,
            _steps=steps,
        )

        hairpin.attach(sink=sink)
        return hairpin

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        start: TemporalAnchor,
        end: TemporalAnchor | None,
        voice: Voice,
        steps: int,
        sink: MutationSink = DIRECT_SINK,
    ) -> Hairpin:
        hairpin = cls(
            id=id,
            _start=start,
            _end=end,
            _voice=voice,
            _steps=steps,
        )

        hairpin.attach(sink=sink)
        return hairpin


@dataclass(kw_only=True, eq=False)
class Slur(VoiceScoped, SpanContext):
    @classmethod
    def create(
        cls,
        *,
        start: TemporalAnchor,
        end: TemporalAnchor | None,
        voice: Voice,
        sink: MutationSink = DIRECT_SINK,
    ) -> Slur:
        slur = cls(_start=start, _end=end, _voice=voice)

        slur.attach(sink=sink)
        return slur

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        start: TemporalAnchor,
        end: TemporalAnchor | None,
        voice: Voice,
        sink: MutationSink = DIRECT_SINK,
    ) -> Slur:
        slur = cls(id=id, _start=start, _end=end, _voice=voice)

        slur.attach(sink=sink)
        return slur
