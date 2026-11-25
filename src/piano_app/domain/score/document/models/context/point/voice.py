from dataclasses import dataclass
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.score.document.models.notation import DynamicMarking

from ..scope import VoiceScoped
from .base import PointContext

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.structural import TemporalAnchor, Voice


@dataclass(kw_only=True, eq=False)
class DynamicChange(VoiceScoped, PointContext):
    _dynamic: DynamicMarking

    @property
    def dynamic(self) -> DynamicMarking:
        return self._dynamic

    @classmethod
    def create(
        cls,
        *,
        start: TemporalAnchor,
        voice: Voice,
        dynamic: DynamicMarking,
        sink: MutationSink = DIRECT_SINK,
    ) -> DynamicChange:
        dynamic_change = cls(_start=start, _voice=voice, _dynamic=dynamic)

        dynamic_change.attach(sink=sink)
        return dynamic_change

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        start: TemporalAnchor,
        voice: Voice,
        dynamic: DynamicMarking,
        sink: MutationSink = DIRECT_SINK,
    ) -> DynamicChange:
        dynamic_change = cls(id=id, _start=start, _voice=voice, _dynamic=dynamic)

        dynamic_change.attach(sink=sink)
        return dynamic_change
