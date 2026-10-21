from dataclasses import dataclass
from fractions import Fraction
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
        end: TemporalAnchor | None,
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
        end: TemporalAnchor | None,
        sink: MutationSink = DIRECT_SINK,
    ) -> SustainHold:
        sustain_hold = cls(id=id, _start=start, _end=end)

        sustain_hold.attach(sink=sink)
        return sustain_hold


def _check_ratio(*, ratio: Fraction) -> None:
    if ratio <= 0:
        raise ValueError("A tempo transition's ratio must be positive.")

    if ratio == 1:
        raise ValueError("A tempo transition's ratio must not be one: it would change nothing.")


@dataclass(kw_only=True, eq=False)
class TempoTransition(SpanContext):
    """A gradual tempo change over a span — accelerando above one, ritardando below one.

    ``ratio`` is the ratio of speed at the span's end to the speed in force at its start, so
    it is independent of any beat unit and the end tempo is derived from whatever tempo the
    span starts from. Score-scoped — no scope mixin.
    """

    _ratio: Fraction

    @property
    def ratio(self) -> Fraction:
        return self._ratio

    def _check_invariants(self) -> None:
        super()._check_invariants()
        _check_ratio(ratio=self._ratio)

    def set_ratio(self, *, ratio: Fraction, sink: MutationSink = DIRECT_SINK) -> None:
        """Change the ratio of speed the transition ends at, keeping the transition itself."""
        _check_ratio(ratio=ratio)
        sink.set_field(self, "_ratio", ratio)

    @classmethod
    def create(
        cls,
        *,
        start: TemporalAnchor,
        end: TemporalAnchor | None,
        ratio: Fraction,
        sink: MutationSink = DIRECT_SINK,
    ) -> TempoTransition:
        tempo_transition = cls(_start=start, _end=end, _ratio=ratio)

        tempo_transition.attach(sink=sink)
        return tempo_transition

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        start: TemporalAnchor,
        end: TemporalAnchor | None,
        ratio: Fraction,
        sink: MutationSink = DIRECT_SINK,
    ) -> TempoTransition:
        tempo_transition = cls(id=id, _start=start, _end=end, _ratio=ratio)

        tempo_transition.attach(sink=sink)
        return tempo_transition
