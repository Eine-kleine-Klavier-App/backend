from dataclasses import dataclass
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.shared.abstract import abstract

from ..base import Context

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.structural import TemporalAnchor


@abstract
@dataclass(kw_only=True, eq=False)
class SpanContext(Context):
    """A context that occupies a range — adds ``end`` on top of ``Context.start``.

    The end is the anchor the range stops at (the 0/0 of the measure after the last one it
    covers), or ``None`` for a range that lasts until the end of the score: nothing follows the
    last measure, so there is no anchor to stop at. (A temporary way to close a range at the
    end of the score, see the decision note ``span-open-end``.)
    """

    _end: TemporalAnchor | None

    @property
    def end(self) -> TemporalAnchor | None:
        return self._end

    def _check_invariants(self) -> None:
        super()._check_invariants()

        if self.end is not None and not self.start.precedes(self.end):
            raise ValueError("Start must precede end.")

    def attach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        super().attach(sink=sink)
        if self.end is not None:
            self.end.add_ending_context(context=self, sink=sink)

    def detach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        if self.end is not None:
            self.end.remove_ending_context(context=self, sink=sink)

        super().detach(sink=sink)

    def set_start(self, *, start: TemporalAnchor, sink: MutationSink = DIRECT_SINK) -> None:
        if self.end is not None and not start.precedes(self.end):
            raise ValueError("Start must precede end.")

        super().set_start(start=start, sink=sink)

    def set_end(self, *, end: TemporalAnchor | None, sink: MutationSink = DIRECT_SINK) -> None:
        """Move the context's end to another anchor, or to the end of the score (``None``),
        keeping the context itself."""
        if end is not None and not self.start.precedes(end):
            raise ValueError("Start must precede end.")

        self.detach(sink=sink)
        sink.set_field(self, "_end", end)
        self.attach(sink=sink)
