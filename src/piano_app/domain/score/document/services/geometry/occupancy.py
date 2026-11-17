from bisect import bisect_left
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

    A scope's layout is built whole on its first read. After that a change marks only the
    children it touched, and the next read lifts each of them out of the measures it was in
    and puts it into the measures it reaches now, in the scope's order.
    """

    def __init__(self, *, spaces: SpacesIndex) -> None:
        self._spaces: SpacesIndex = spaces
        self._layouts: dict[RhythmicContainerParent, dict[Measure, list[RhythmicContainer]]] = {}
        # the measures each child sits in within its scope's layout, to lift it out again
        self._reach: dict[RhythmicContainerParent, dict[RhythmicContainer, Sequence[Measure]]] = {}
        self._dirty: dict[RhythmicContainerParent, set[RhythmicContainer]] = {}

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
            layout = self._build(scope=scope)
        elif scope in self._dirty:
            self._heal(scope=scope, layout=layout)

        return layout.get(measure, [])

    def invalidate_measures(self) -> None:
        # a measure shifts every later one, and may change which measures a container
        # crossing a barline reaches — anywhere, so every layout goes and is built again
        self._layouts.clear()
        self._reach.clear()
        self._dirty.clear()

    def invalidate_anchor(self, *, anchor: TemporalAnchor) -> None:
        for container in anchor.containers:
            self.invalidate_child(scope=container.parent, child=container)

    def invalidate_leaf(self, *, leaf: LeafRhythmicContainer) -> None:
        self.invalidate_child(scope=leaf.parent, child=leaf)

    def invalidate_child(self, *, scope: RhythmicContainerParent, child: RhythmicContainer) -> None:
        # a scope nobody has read has no layout to keep right
        if scope in self._layouts:
            self._dirty.setdefault(scope, set()).add(child)

    def invalidate_group(self, *, group: GroupRhythmicContainer) -> None:
        self.invalidate_child(scope=group.parent, child=group)

        # a group's scale reaches everything under it: which measures each nested container
        # reaches into
        pending: list[GroupRhythmicContainer] = [group]
        while pending:
            nested: GroupRhythmicContainer = pending.pop()
            self._drop(scope=nested)
            pending.extend(
                child for child in nested.children if isinstance(child, GroupRhythmicContainer)
            )

    def _build(self, *, scope: RhythmicContainerParent) -> dict[Measure, list[RhythmicContainer]]:
        scale: Fraction = self._spaces.scale_of(scope=scope)

        layout: dict[Measure, list[RhythmicContainer]] = {}
        reach: dict[RhythmicContainer, Sequence[Measure]] = {}
        for child in scope.children:
            reach[child] = self._measures_reached_by(child=child, scale=scale)
            for reached in reach[child]:
                layout.setdefault(reached, []).append(child)

        self._layouts[scope] = layout
        self._reach[scope] = reach

        return layout

    def _heal(
        self,
        *,
        scope: RhythmicContainerParent,
        layout: dict[Measure, list[RhythmicContainer]],
    ) -> None:
        reach: dict[RhythmicContainer, Sequence[Measure]] = self._reach[scope]
        dirty: set[RhythmicContainer] = self._dirty.pop(scope)

        # a read that cannot answer leaves the layout half healed, so it goes and is built
        # again by the next read
        try:
            for child in dirty:
                for reached in reach.pop(child, ()):
                    layout[reached].remove(child)

            scale: Fraction = self._spaces.scale_of(scope=scope)
            places: dict[RhythmicContainer, int] = {
                child: place for place, child in enumerate(scope.children)
            }
            for child in dirty:
                # a child the scope no longer holds is only lifted out
                if child not in places:
                    continue

                reach[child] = self._measures_reached_by(child=child, scale=scale)
                for reached in reach[child]:
                    children: list[RhythmicContainer] = layout.setdefault(reached, [])
                    children.insert(
                        bisect_left(children, places[child], key=places.__getitem__), child
                    )
        except Exception:
            self._drop(scope=scope)
            raise

    def _measures_reached_by(
        self, *, child: RhythmicContainer, scale: Fraction
    ) -> Sequence[Measure]:
        anchor: TemporalAnchor = child.start_anchor
        end: Fraction = (
            self._spaces.anchor_position(anchor=anchor) + child.occupied_size.fraction * scale
        )

        return self._spaces.measures_from(measure=anchor.measure, end=end)

    def _drop(self, *, scope: RhythmicContainerParent) -> None:
        self._layouts.pop(scope, None)
        self._reach.pop(scope, None)
        self._dirty.pop(scope, None)
