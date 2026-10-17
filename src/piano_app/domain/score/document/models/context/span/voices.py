from dataclasses import dataclass
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.score.document.models.notation import HairpinType

from ..scope import VoicesScoped
from .base import SpanContext

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.structural import TemporalAnchor, Voice


@dataclass(kw_only=True, eq=False)
class Hairpin(VoicesScoped, SpanContext):
    _hairpin_type: HairpinType

    @property
    def hairpin_type(self) -> HairpinType:
        return self._hairpin_type

    @classmethod
    def create(
        cls,
        *,
        start: TemporalAnchor,
        end: TemporalAnchor,
        voices: list[Voice],
        hairpin_type: HairpinType,
        sink: MutationSink = DIRECT_SINK,
    ) -> Hairpin:
        hairpin = cls(
            _start=start,
            _end=end,
            _voices=voices,
            _hairpin_type=hairpin_type,
        )

        hairpin.attach(sink=sink)
        return hairpin

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        start: TemporalAnchor,
        end: TemporalAnchor,
        voices: list[Voice],
        hairpin_type: HairpinType,
        sink: MutationSink = DIRECT_SINK,
    ) -> Hairpin:
        hairpin = cls(
            id=id,
            _start=start,
            _end=end,
            _voices=voices,
            _hairpin_type=hairpin_type,
        )

        hairpin.attach(sink=sink)
        return hairpin


@dataclass(kw_only=True, eq=False)
class Slur(VoicesScoped, SpanContext):
    @classmethod
    def create(
        cls,
        *,
        start: TemporalAnchor,
        end: TemporalAnchor,
        voices: list[Voice],
        sink: MutationSink = DIRECT_SINK,
    ) -> Slur:
        slur = cls(_start=start, _end=end, _voices=voices)

        slur.attach(sink=sink)
        return slur

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        start: TemporalAnchor,
        end: TemporalAnchor,
        voices: list[Voice],
        sink: MutationSink = DIRECT_SINK,
    ) -> Slur:
        slur = cls(id=id, _start=start, _end=end, _voices=voices)

        slur.attach(sink=sink)
        return slur
