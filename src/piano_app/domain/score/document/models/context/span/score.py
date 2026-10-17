from dataclasses import dataclass
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink

from .base import SpanContext

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.structural import TemporalAnchor


@dataclass(kw_only=True, eq=False)
class SustainHold(SpanContext):
    """Score-scoped — no scope mixin, extends SpanContext directly."""

    @classmethod
    def create(
        cls,
        *,
        start: TemporalAnchor,
        end: TemporalAnchor,
        sink: MutationSink = DIRECT_SINK,
    ) -> SustainHold:
        sustain_hold = cls(_start=start, _end=end)

        sustain_hold.attach(sink=sink)
        return sustain_hold

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        start: TemporalAnchor,
        end: TemporalAnchor,
        sink: MutationSink = DIRECT_SINK,
    ) -> SustainHold:
        sustain_hold = cls(id=id, _start=start, _end=end)

        sustain_hold.attach(sink=sink)
        return sustain_hold
