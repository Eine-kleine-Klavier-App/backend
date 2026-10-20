from collections.abc import Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.score.document.models.notation import RhythmicSize

from .base import RhythmicContainer
from .parent import RhythmicContainerParent

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.structural import Measure, TemporalAnchor


@dataclass(slots=True, kw_only=True, eq=False)
class GroupRhythmicContainer(RhythmicContainer):
    # may be empty at any time: the group starts at its own anchor, not at a child
    _children: list[RhythmicContainer] = field(default_factory=list)

    @property
    def children(self) -> Sequence[RhythmicContainer]:
        return self._children

    def _check_invariants(self) -> None:
        super()._check_invariants()

        # a group sounding exactly as long as it is written scales nothing
        if self.written_size.fraction == self.occupied_size.fraction:
            raise ValueError("A rhythmic group must differ in written and occupied size.")

    @classmethod
    def create(
        cls,
        *,
        parent: RhythmicContainerParent,
        anchor: TemporalAnchor,
        written_size: RhythmicSize,
        occupied_size: RhythmicSize,
        sink: MutationSink = DIRECT_SINK,
    ) -> GroupRhythmicContainer:
        group: GroupRhythmicContainer = cls(
            written_size=written_size,
            occupied_size=occupied_size,
            _parent=parent,
            _anchor=anchor,
        )

        group.attach(sink=sink)
        return group

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        parent: RhythmicContainerParent,
        anchor: TemporalAnchor,
        written_size: RhythmicSize,
        occupied_size: RhythmicSize,
        sink: MutationSink = DIRECT_SINK,
    ) -> GroupRhythmicContainer:
        group: GroupRhythmicContainer = cls(
            id=id,
            written_size=written_size,
            occupied_size=occupied_size,
            _parent=parent,
            _anchor=anchor,
        )

        group.attach(sink=sink)
        return group

    def split_at(
        self,
        *,
        anchor: TemporalAnchor,
        first_written_size: RhythmicSize,
        first_occupied_size: RhythmicSize,
        second_written_size: RhythmicSize,
        second_occupied_size: RhythmicSize,
        sink: MutationSink = DIRECT_SINK,
    ) -> GroupRhythmicContainer:
        """Split the group in two at ``anchor``, in one step, and return the second part.

        The group keeps the first part's sizes; the second part is a new group starting at
        ``anchor`` in the same parent, holding every child starting at or after it. Both
        parts keep the group's ratio and together take exactly its room. Everything is
        checked before anything changes: the sizes, that ``anchor`` lies strictly inside the
        room the group takes, and that each part holds its children; which instant to split
        at is the caller's.
        """
        written: Fraction = self.written_size.fraction
        occupied: Fraction = self.occupied_size.fraction
        first_written: Fraction = first_written_size.fraction
        first_occupied: Fraction = first_occupied_size.fraction

        if (
            first_written + second_written_size.fraction != written
            or first_occupied + second_occupied_size.fraction != occupied
        ):
            raise ValueError("The parts of a split group must take exactly its sizes.")

        if first_written * occupied != first_occupied * written:
            raise ValueError("The parts of a split group must keep its ratio.")

        # how far the anchor lies after the group's start, measure by measure: it must fall
        # strictly inside the room the group takes
        start: TemporalAnchor = self._anchor
        if not start.precedes(anchor):
            raise ValueError("A group is split only at an anchor strictly inside it.")

        distance: Fraction = anchor.position.value - start.position.value
        measure: Measure | None = start.measure
        while measure is not None and measure is not anchor.measure:
            distance += measure.time_signature.fraction
            measure = measure.next_measure

        if distance >= occupied:
            raise ValueError("A group is split only at an anchor strictly inside it.")

        # the constructor guards the second part's own invariant before anything changes
        second: GroupRhythmicContainer = GroupRhythmicContainer(
            written_size=second_written_size,
            occupied_size=second_occupied_size,
            _parent=self._parent,
            _anchor=anchor,
        )

        moved: list[RhythmicContainer] = [
            child for child in self._children if not child.start_anchor.precedes(anchor)
        ]
        kept_size: Fraction = sum(
            (child.occupied_size.fraction for child in self._children if child not in moved),
            Fraction(0),
        )
        if kept_size > first_written:
            raise ValueError("The first part of a split group cannot hold its children.")

        moved_size: Fraction = sum((child.occupied_size.fraction for child in moved), Fraction(0))
        if moved_size > second_written_size.fraction:
            raise ValueError("The second part of a split group cannot hold its children.")

        # the moved children name the second part before it is listed, so its anchor lists
        # it before the children it holds starting there
        for child in moved:
            self.remove_child(child=child, sink=sink)
            sink.set_field(child, "_parent", second)

        sink.set_field(self, "written_size", first_written_size)
        sink.set_field(self, "occupied_size", first_occupied_size)
        second.attach(sink=sink)

        for child in moved:
            second.add_child(child=child, sink=sink)

        return second

    def add_child(
        self,
        *,
        child: RhythmicContainer,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if child.parent is not self:
            raise ValueError("Cannot add child that belongs to another group.")

        if child in self._children:
            return

        occupied_children_size: Fraction = (
            sum(
                (existing_child.occupied_size.fraction for existing_child in self._children),
                Fraction(0, 1),
            )
            + child.occupied_size.fraction
        )

        if occupied_children_size > self.written_size.fraction:
            raise ValueError(
                "GroupRhythmicContainer cannot contain children whose occupied "
                "size exceeds its written size."
            )

        # ordered insertion
        index: int = sum(1 for existing in self._children if existing.precedes(child))
        sink.list_insert(self, "_children", index, child)

    def remove_child(
        self,
        *,
        child: RhythmicContainer,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if child.parent is not self:
            raise ValueError("Cannot remove child that does not belong to this group.")

        if child not in self._children:
            return

        sink.list_remove(self, "_children", child)
