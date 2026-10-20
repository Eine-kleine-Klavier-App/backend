from collections.abc import Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.base import ScoreEntity
from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.context import Context, SpanContext
    from piano_app.domain.score.document.models.structural.jump import Jump
    from piano_app.domain.score.document.models.structural.measure import Measure
    from piano_app.domain.score.document.models.structural.rhythm.metric import (
        RhythmicContainer,
    )


@dataclass(frozen=True, slots=True, kw_only=True, order=True)
class MeasurePosition:
    # value is measured in whole notes (whole = 1).
    # it is a default unit in the system.
    value: Fraction

    def __post_init__(self) -> None:
        # validity of the position itself.
        # compatibility with a measure is checked
        # when adding the anchor with this position to a measure.
        if self.value < 0:
            raise ValueError("Measure position cannot be negative.")

    @classmethod
    def of(cls, *, numerator: int, denominator: int) -> MeasurePosition:
        return cls(value=Fraction(numerator, denominator))

    @classmethod
    def of_fraction(cls, *, fraction: Fraction) -> MeasurePosition:
        return cls(value=fraction)


# the first instant of every measure — where a barline falls
MEASURE_START: MeasurePosition = MeasurePosition(value=Fraction(0))


@dataclass(slots=True, kw_only=True, eq=False)
class TemporalAnchor(ScoreEntity):
    _position: MeasurePosition
    _measure: Measure

    # every rhythmic container starting here — leaves and groups, of every voice; within
    # one scope at most one, nested containers starting at the same instant live in
    # different scopes. Each is listed after the containers holding it, which is the order
    # restoring a stored document rebuilds them in.
    _containers: list[RhythmicContainer] = field(default_factory=list)

    _starting_contexts: list[Context] = field(default_factory=list)
    _ending_contexts: list[SpanContext] = field(default_factory=list)
    # the jumps leaving from here and the jumps landing here, each at its other end somewhere else
    _departing_jumps: list[Jump] = field(default_factory=list)
    _arriving_jumps: list[Jump] = field(default_factory=list)

    @property
    def position(self) -> MeasurePosition:
        return self._position

    @property
    def measure(self) -> Measure:
        return self._measure

    @property
    def containers(self) -> Sequence[RhythmicContainer]:
        return self._containers

    @property
    def starting_contexts(self) -> Sequence[Context]:
        return self._starting_contexts

    @property
    def ending_contexts(self) -> Sequence[SpanContext]:
        return self._ending_contexts

    @property
    def departing_jumps(self) -> Sequence[Jump]:
        return self._departing_jumps

    @property
    def arriving_jumps(self) -> Sequence[Jump]:
        return self._arriving_jumps

    @property
    def is_orphan(self) -> bool:
        return (
            not self._containers
            and not self._starting_contexts
            and not self._ending_contexts
            and not self._departing_jumps
            and not self._arriving_jumps
        )

    @classmethod
    def create(
        cls,
        *,
        measure: Measure,
        position: MeasurePosition,
        sink: MutationSink = DIRECT_SINK,
    ) -> TemporalAnchor:
        anchor: TemporalAnchor = cls(_position=position, _measure=measure)

        anchor.attach(sink=sink)
        return anchor

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        measure: Measure,
        position: MeasurePosition,
        sink: MutationSink = DIRECT_SINK,
    ) -> TemporalAnchor:
        anchor: TemporalAnchor = cls(id=id, _position=position, _measure=measure)

        anchor.attach(sink=sink)
        return anchor

    def attach(
        self,
        *,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        self._measure.add_anchor(anchor=self, sink=sink)

    def detach(
        self,
        *,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        self._measure.remove_anchor(anchor=self, sink=sink)

    def move_to(
        self,
        *,
        measure: Measure,
        position: MeasurePosition,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        """Move the anchor to ``position`` in ``measure``, keeping it and everything that
        starts or ends at it.

        Checked before anything changes: the measure must hold the position, have no other
        anchor there, and the anchor must stay between the anchors before and after it on
        the timeline — the lists ordered by where their entries start (a scope's children, a
        voice's or staff's contexts) are not reordered, so a move past a neighbouring anchor
        would break them. Only the measures' anchor lists change.
        """
        if self not in self._measure.anchors:
            raise ValueError("Cannot move an anchor that is not in its measure.")

        if not measure.holds(position=position):
            raise ValueError(
                f"Anchor position {position} lies at or beyond the end of the measure "
                f"(length {measure.time_signature.fraction})."
            )

        if any(other is not self and other.position == position for other in measure.anchors):
            raise ValueError(f"Anchor with position {position} already exists.")

        # the neighbouring anchors on the timeline: in this measure, else the nearest measure
        # holding any
        siblings: Sequence[TemporalAnchor] = self._measure.anchors
        index: int = siblings.index(self)

        previous: TemporalAnchor | None = siblings[index - 1] if index > 0 else None
        earlier: Measure | None = self._measure.prev_measure
        while previous is None and earlier is not None:
            previous = earlier.anchors[-1] if earlier.anchors else None
            earlier = earlier.prev_measure

        following: TemporalAnchor | None = (
            siblings[index + 1] if index + 1 < len(siblings) else None
        )
        later: Measure | None = self._measure.next_measure
        while following is None and later is not None:
            following = later.anchors[0] if later.anchors else None
            later = later.next_measure

        if (
            previous is not None
            and not previous.precedes_or_equals_position(measure=measure, position=position)
        ) or (
            following is not None
            and following.precedes_or_equals_position(measure=measure, position=position)
        ):
            raise ValueError("An anchor cannot move past its neighbouring anchors on the timeline.")

        self.detach(sink=sink)
        sink.set_field(self, "_measure", measure)
        sink.set_field(self, "_position", position)
        self.attach(sink=sink)

    def precedes(self, other: TemporalAnchor) -> bool:
        """Whether this anchor comes strictly before ``other`` on the timeline —
        an earlier measure, or the same measure at an earlier position."""
        if self._measure is other._measure:
            return self.position < other.position

        return self._measure.precedes(other._measure)

    def precedes_or_equals_position(
        self,
        *,
        measure: Measure,
        position: MeasurePosition,
    ) -> bool:
        if self._measure.precedes(measure):
            return True

        return self._measure is measure and self.position <= position

    def add_container(
        self,
        *,
        container: RhythmicContainer,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if container.start_anchor is not self:
            raise ValueError("Cannot add container starting at a different anchor.")

        if container in self._containers:
            return

        # before the first container it holds, so it stays after every one holding it
        index: int = next(
            (
                index
                for index, existing in enumerate(self._containers)
                if container.is_ancestor_of(existing)
            ),
            len(self._containers),
        )
        sink.list_insert(self, "_containers", index, container)

    def remove_container(
        self,
        *,
        container: RhythmicContainer,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if container.start_anchor is not self:
            raise ValueError("Cannot remove container starting at a different anchor.")

        if container not in self._containers:
            return

        sink.list_remove(self, "_containers", container)

    def add_starting_context(
        self,
        *,
        context: Context,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if context.start is not self:
            raise ValueError("Cannot add context that does not start at this anchor.")

        if context in self._starting_contexts:
            return

        sink.list_append(self, "_starting_contexts", context)

    def remove_starting_context(
        self,
        *,
        context: Context,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if context.start is not self:
            raise ValueError("Cannot remove context that does not start at this anchor.")

        if context not in self._starting_contexts:
            return

        sink.list_remove(self, "_starting_contexts", context)

    def add_ending_context(
        self,
        *,
        context: SpanContext,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if context.end is not self:
            raise ValueError("Cannot add context that does not end at this anchor.")

        if context in self._ending_contexts:
            return

        sink.list_append(self, "_ending_contexts", context)

    def remove_ending_context(
        self,
        *,
        context: SpanContext,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if context.end is not self:
            raise ValueError("Cannot remove context that does not end at this anchor.")

        if context not in self._ending_contexts:
            return

        sink.list_remove(self, "_ending_contexts", context)

    def add_departing_jump(
        self,
        *,
        jump: Jump,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if jump.source is not self:
            raise ValueError("Cannot add a jump that does not leave from this anchor.")

        if jump in self._departing_jumps:
            return

        sink.list_append(self, "_departing_jumps", jump)

    def remove_departing_jump(
        self,
        *,
        jump: Jump,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if jump.source is not self:
            raise ValueError("Cannot remove a jump that does not leave from this anchor.")

        if jump not in self._departing_jumps:
            return

        sink.list_remove(self, "_departing_jumps", jump)

    def add_arriving_jump(
        self,
        *,
        jump: Jump,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if jump.target is not self:
            raise ValueError("Cannot add a jump that does not land at this anchor.")

        if jump in self._arriving_jumps:
            return

        sink.list_append(self, "_arriving_jumps", jump)

    def remove_arriving_jump(
        self,
        *,
        jump: Jump,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if jump.target is not self:
            raise ValueError("Cannot remove a jump that does not land at this anchor.")

        if jump not in self._arriving_jumps:
            return

        sink.list_remove(self, "_arriving_jumps", jump)
