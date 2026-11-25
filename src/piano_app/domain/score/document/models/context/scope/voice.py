from dataclasses import dataclass
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.shared.abstract import abstract

from ..base import Context

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.structural import Voice


@abstract
@dataclass(kw_only=True, eq=False)
class VoiceScoped(Context):
    """Scope axis: a context tied to one voice.

    Orthogonal to the Point/Span form axis — combined with either via multiple
    inheritance between two dataclass role bases.
    """

    _voice: Voice

    @property
    def voice(self) -> Voice:
        return self._voice

    def attach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        super().attach(sink=sink)
        self.voice.add_context(context=self, sink=sink)

    def detach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        self.voice.remove_context(context=self, sink=sink)
        super().detach(sink=sink)
