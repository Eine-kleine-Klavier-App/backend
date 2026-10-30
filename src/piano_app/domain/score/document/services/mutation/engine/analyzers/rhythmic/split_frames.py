from fractions import Fraction

from piano_app.domain.score.document.models.notation import (
    DottedRhythmicValue,
    RhythmicSize,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural import (
    MEASURE_START,
    Measure,
    TemporalAnchor,
    Voice,
)
from piano_app.domain.score.document.models.structural.rhythm import GroupRhythmicContainer
from piano_app.domain.score.document.services.geometry import Point, Span
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.analyzers.base import (
    find_or_create_anchor,
)
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.actions.rhythmic import (
    SplitRhythmicGroupAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    SplitRhythmicGroupRequest,
)


def split_crossing_groups(*, measure: Measure, geometry: ScoreGeometry) -> MutationAnalysis:
    """Splits every group of every voice crossing the barline at the start of a measure.

    Only the groups standing in their voice are found here; each split splits the groups
    nested in it. A group crossing the barline starts in an earlier measure, so it is found
    on the anchors of the measures before it. Decided before the first yield: each split
    touches only its own group.
    """
    barline: Fraction = (
        Point(frame=geometry.of_measure(measure=measure), value=Fraction(0))
        .to(frame=geometry.root)
        .value
    )

    crossing: list[GroupRhythmicContainer] = []
    earlier: Measure | None = measure.prev_measure
    while earlier is not None:
        for anchor in earlier.anchors:
            for container in anchor.containers:
                if not isinstance(container, GroupRhythmicContainer) or not isinstance(
                    container.parent, Voice
                ):
                    continue

                reach: Span = geometry.global_span_of(container=container)
                if reach.start < barline < reach.end:
                    crossing.append(container)

        earlier = earlier.prev_measure

    for group in crossing:
        yield SplitRhythmicGroupRequest(group=group, measure=measure)


class SplitRhythmicGroupAnalyzer:
    """Splits a group in two at a barline it crosses (measure-operations,
    time-signature-change).

    Both parts keep the group's ratio: each takes its share of the group's room and is
    written as that share times written / occupied. The group itself becomes the part
    before the barline; the part from the barline on is a new group in the same scope,
    holding every child starting from the barline with its content and relations — all in
    one model step, sent back as the request's result. Content is cut at every barline, so
    no leaf is cut here; a group nested in it and crossing the barline is split the same
    way first, so its second part moves with the rest.

    Everything geometric is decided before the first yield; only sizes, the measure and
    entities are carried across.
    """

    def analyze(
        self,
        *,
        request: SplitRhythmicGroupRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        group: GroupRhythmicContainer = request.group
        measure: Measure = request.measure

        barline: Point = Point(frame=geometry.of_measure(measure=measure), value=Fraction(0))
        room: Span = geometry.span_of(container=group)
        occupied_before: Fraction = barline.to(frame=room.frame).value - room.start
        if not 0 < occupied_before < room.length:
            raise ValueError("A group is split only at a barline it crosses.")

        # the share of its room, read in its own frame: occupied_before * written / occupied
        written_before: Fraction = barline.to(frame=geometry.of_group(group=group)).value

        nested: list[GroupRhythmicContainer] = []
        for child, span in geometry.contents_of(scope=group):
            if not span.start < written_before < span.end:
                continue

            if not isinstance(child, GroupRhythmicContainer):
                raise ValueError("A leaf crosses a barline: content is cut at every barline.")

            nested.append(child)

        first_written: RhythmicSize = _spell(
            length=written_before,
            unit=group.written_size.value,
        )
        first_occupied: RhythmicSize = _spell(
            length=occupied_before,
            unit=group.occupied_size.value,
        )
        second_written: RhythmicSize = _spell(
            length=group.written_size.fraction - written_before,
            unit=group.written_size.value,
        )
        second_occupied: RhythmicSize = _spell(
            length=room.length - occupied_before,
            unit=group.occupied_size.value,
        )

        for inner in nested:
            yield SplitRhythmicGroupRequest(group=inner, measure=measure)

        anchor: TemporalAnchor = yield from find_or_create_anchor(
            measure=measure, position=MEASURE_START
        )

        # one model step: no request ever sees the group shrunk with children past its end
        yield SplitRhythmicGroupAction(
            group=group,
            anchor=anchor,
            first_written_size=first_written,
            first_occupied_size=first_occupied,
            second_written_size=second_written,
            second_occupied_size=second_occupied,
        )


def _spell(*, length: Fraction, unit: DottedRhythmicValue) -> RhythmicSize:
    """A part's size: a count of the group's own unit when it divides the length, else of
    the longest plain value that does."""
    candidates: list[DottedRhythmicValue] = [
        unit,
        *(DottedRhythmicValue(value=rhythmic_value) for rhythmic_value in RhythmicValue),
    ]
    for candidate in candidates:
        count: Fraction = length / candidate.fraction
        if count.denominator == 1:
            return RhythmicSize(value=candidate, count=count.numerator)

    raise MutationRejectedError(f"A part of a split group cannot be written as {length}.")
