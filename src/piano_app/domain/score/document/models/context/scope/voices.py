from dataclasses import dataclass
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.shared.abstract import abstract

from ..base import Context

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.structural import Voice


@abstract
@dataclass(kw_only=True, eq=False)
class VoicesScoped(Context):
    """Scope axis: a context tied to a set of voices.

    Orthogonal to the Point/Span form axis — combined with either via multiple
    inheritance between two dataclass role bases.
    """

    _voices: list[Voice]

    @property
    def voices(self) -> list[Voice]:
        return self._voices

    def _check_invariants(self) -> None:
        super()._check_invariants()

        if not self._voices:
            raise ValueError("Voices scope must contain at least one voice.")

        if len(self._voices) != len(set(self._voices)):
            raise ValueError("Voices scope must not repeat a voice.")

    def attach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        super().attach(sink=sink)
        for voice in self.voices:
            voice.add_context(context=self, sink=sink)

    def detach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        for voice in self.voices:
            voice.remove_context(context=self, sink=sink)
        super().detach(sink=sink)
