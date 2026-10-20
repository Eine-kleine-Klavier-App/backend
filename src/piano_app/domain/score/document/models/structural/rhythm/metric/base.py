from dataclasses import dataclass
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.base import ScoreEntity
from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.score.document.models.notation import RhythmicSize
from piano_app.domain.shared.abstract import abstract

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.structural import TemporalAnchor

    from .parent import RhythmicContainerParent


@abstract
@dataclass(slots=True, kw_only=True, eq=False)
class RhythmicContainer(ScoreEntity):
    written_size: RhythmicSize  # capacity of this container
    occupied_size: RhythmicSize  # actual size of this container

    _parent: RhythmicContainerParent
    _anchor: TemporalAnchor

    @property
    def parent(self) -> RhythmicContainerParent:
        return self._parent

    @property
    def start_anchor(self) -> TemporalAnchor:
        """The anchor where this container begins — its own, whatever it contains."""
        return self._anchor

    def precedes(self, other: RhythmicContainer) -> bool:
        return self.start_anchor.precedes(other.start_anchor)

    def is_ancestor_of(self, other: RhythmicContainer) -> bool:
        """Whether ``other`` lies inside this container, at any depth."""
        parent: RhythmicContainerParent = other.parent
        while isinstance(parent, RhythmicContainer):
            if parent is self:
                return True

            parent = parent.parent

        return False

    def attach(
        self,
        *,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        self._parent.add_child(child=self, sink=sink)
        self._anchor.add_container(container=self, sink=sink)

    def detach(
        self,
        *,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        self._anchor.remove_container(container=self, sink=sink)
        self._parent.remove_child(child=self, sink=sink)
