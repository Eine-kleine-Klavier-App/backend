from dataclasses import dataclass
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.base import ScoreEntity
from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.shared.abstract import abstract

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.structural import TemporalAnchor


@abstract
@dataclass(kw_only=True, eq=False)
class Context(ScoreEntity):
    """Role base: an event placed directly on the timeline.

    Unlike ``Relation``, a context IS its own placement — position lives on the
    concrete subclass itself, not behind a separate wrapper entity. Every context
    starts somewhere; ``SpanContext`` additionally ends somewhere.
    """

    _start: TemporalAnchor

    @property
    def start(self) -> TemporalAnchor:
        return self._start

    def precedes(self, other: Context) -> bool:
        return self.start.precedes(other.start)

    def attach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        self.start.add_starting_context(context=self, sink=sink)

    def detach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        self.start.remove_starting_context(context=self, sink=sink)

    def set_start(self, *, start: TemporalAnchor, sink: MutationSink = DIRECT_SINK) -> None:
        """Move the context's start to another anchor, keeping the context itself.

        Detached and attached again around the change, so every index ordered by the
        start sees it at its new place.
        """
        self.detach(sink=sink)
        sink.set_field(self, "_start", start)
        self.attach(sink=sink)
