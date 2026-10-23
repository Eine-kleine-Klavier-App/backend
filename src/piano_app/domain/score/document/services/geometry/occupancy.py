from collections.abc import Sequence
from fractions import Fraction

from piano_app.domain.score.document.models.structural import Measure, TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.indexing import Index

from .spaces import SpacesIndex


class OccupancyIndex(Index):
    """What lies in each scope, by the measures it reaches into, built lazily over the
    spaces and kept until told what changed.

    A scope's layout is healed on its own when read dirty; a dirty one is simply absent.
    """

    def __init__(self, *, spaces: SpacesIndex) -> None:
        self._spaces: SpacesIndex = spaces
        self._layouts: dict[RhythmicContainerParent, dict[Measure, list[RhythmicContainer]]] = {}

    def find_children_in(
        self,
        *,
        scope: RhythmicContainerParent,
        measure: Measure,
    ) -> Sequence[RhythmicContainer]:
        """The scope's children whose room on the timeline reaches into the measure, in the
        scope's order. Half-open: a child ending on a barline does not reach past it."""
        layout: dict[Measure, list[RhythmicContainer]] | None = self._layouts.get(scope)
        if layout is None:
            scale: Fraction = self._spaces.scale_of(scope=scope)

            layout = {}
            for child in scope.children:
                anchor: TemporalAnchor = child.start_anchor
                end: Fraction = (
                    self._spaces.anchor_position(anchor=anchor)
                    + child.occupied_size.fraction * scale
                )
                for reached in self._spaces.measures_from(measure=anchor.measure, end=end):
                    layout.setdefault(reached, []).append(child)

            self._layouts[scope] = layout

        return layout.get(measure, [])

    def invalidate_measures(self) -> None:
        # a measure shifts every later one, and may change which measures a container
        # crossing a barline reaches — anywhere, so every layout goes and heals per scope
        self._layouts.clear()

    def invalidate_anchor(self, *, anchor: TemporalAnchor) -> None:
        for container in anchor.containers:
            self._layouts.pop(container.parent, None)

    def invalidate_leaf(self, *, leaf: LeafRhythmicContainer) -> None:
        self._layouts.pop(leaf.parent, None)

    def invalidate_scope(self, *, scope: RhythmicContainerParent) -> None:
        self._layouts.pop(scope, None)

    def invalidate_group(self, *, group: GroupRhythmicContainer) -> None:
        self._layouts.pop(group.parent, None)

        # a group's scale reaches everything under it: which measures each nested container
        # reaches into
        pending: list[GroupRhythmicContainer] = [group]
        while pending:
            nested: GroupRhythmicContainer = pending.pop()
            self._layouts.pop(nested, None)
            pending.extend(
                child for child in nested.children if isinstance(child, GroupRhythmicContainer)
            )
