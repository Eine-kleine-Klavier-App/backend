from dataclasses import dataclass
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.notation import (
    DottedRhythmicValue,
    RhythmicSize,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    Staff,
    TemporalAnchor,
    Voice,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.geometry import (
    OutsideFrameError,
    Point,
    Span,
    UnreachableFrameError,
    footprint,
    overflow,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry

from ..scene import tell_geometry


def _size(value: RhythmicValue, count: int = 1) -> RhythmicSize:
    return RhythmicSize(value=DottedRhythmicValue(value=value), count=count)


@dataclass(frozen=True, slots=True, kw_only=True)
class _Score:
    """Three 4/4 measures in one voice: a quarter on beat 1, then a triplet on beat 2 —
    three written eighths squeezed into a quarter."""

    document: ScoreDocument
    voice: Voice
    measures: list[Measure]
    quarter: LeafRhythmicContainer
    triplet: GroupRhythmicContainer
    triplet_leaves: list[LeafRhythmicContainer]


@pytest.fixture
def score() -> _Score:
    measures: list[Measure] = [Measure.create() for _ in range(3)]
    voice: Voice = Voice()
    document: ScoreDocument = ScoreDocument.create(
        voices=[voice], staffs=[Staff()], measures=measures
    )

    # the triplet starts at its own anchor; its first leaf starts at the same instant and
    # shares it
    starts: list[TemporalAnchor] = [
        TemporalAnchor.create(
            measure=measures[0],
            position=MeasurePosition.of_fraction(fraction=Fraction(1, 4) + Fraction(index, 12)),
        )
        for index in range(3)
    ]
    triplet: GroupRhythmicContainer = GroupRhythmicContainer.create(
        parent=voice,
        anchor=starts[0],
        written_size=_size(RhythmicValue.EIGHTH, 3),
        occupied_size=_size(RhythmicValue.QUARTER),
    )
    triplet_leaves: list[LeafRhythmicContainer] = [
        LeafRhythmicContainer.create(
            parent=triplet,
            anchor=start,
            size=_size(RhythmicValue.EIGHTH),
        )
        for start in starts
    ]
    quarter: LeafRhythmicContainer = LeafRhythmicContainer.create(
        parent=voice,
        anchor=TemporalAnchor.create(
            measure=measures[0], position=MeasurePosition.of(numerator=0, denominator=1)
        ),
        size=_size(RhythmicValue.QUARTER),
    )

    return _Score(
        document=document,
        voice=voice,
        measures=measures,
        quarter=quarter,
        triplet=triplet,
        triplet_leaves=triplet_leaves,
    )


@pytest.mark.unit
def test_two_geometries_of_one_document_share_its_timeline(score: _Score) -> None:
    """Frames built by separate geometries over one document combine: they stand for the
    same timeline."""
    first: ScoreGeometry = ScoreGeometry(document=score.document)
    second: ScoreGeometry = ScoreGeometry(document=score.document)

    assert first.root == second.root
    assert first.global_span_of(container=score.quarter) == second.global_span_of(
        container=score.quarter
    )


@pytest.mark.unit
def test_a_written_eighth_inside_a_triplet_lasts_a_twelfth(score: _Score) -> None:
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)

    globals_: list[Span] = [
        geometry.global_span_of(container=leaf) for leaf in score.triplet_leaves
    ]

    assert [span.length for span in globals_] == [Fraction(1, 12)] * 3
    assert [span.start for span in globals_] == [Fraction(1, 4), Fraction(1, 3), Fraction(5, 12)]


@pytest.mark.unit
def test_a_leaf_inside_a_group_is_placed_by_its_own_anchor(score: _Score) -> None:
    """Inside a group, a leaf sits at its own anchor restated in the group's written
    units — the same rule as in a voice."""
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)

    assert [geometry.span_of(container=leaf).start for leaf in score.triplet_leaves] == [
        Fraction(0),
        Fraction(1, 8),
        Fraction(1, 4),
    ]


@pytest.mark.unit
def test_a_group_agrees_with_itself_from_within_and_from_without(score: _Score) -> None:
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)

    assert footprint(frame=geometry.of_group(group=score.triplet)) == geometry.span_of(
        container=score.triplet
    )


@pytest.mark.unit
def test_descending_finds_the_innermost_scope_and_restates_the_point(score: _Score) -> None:
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)

    for position, expected_scope, expected_local in (
        (Fraction(0), score.voice, Fraction(0)),
        (Fraction(1, 4), score.triplet, Fraction(0)),
        (Fraction(1, 3), score.triplet, Fraction(1, 8)),
        (Fraction(5, 12), score.triplet, Fraction(1, 4)),
        (Fraction(1, 2), score.voice, Fraction(1, 2)),
    ):
        scope, local = geometry.deepest_scope_at(
            point=Span(frame=geometry.root, start=position, length=Fraction(1, 64)).start_point,
            voice=score.voice,
        )

        assert scope is expected_scope
        assert local.value == expected_local


@pytest.mark.unit
def test_a_span_crossing_a_barline_comes_back_in_pieces(score: _Score) -> None:
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)
    crossing: Span = Span(frame=geometry.root, start=Fraction(7, 8), length=Fraction(1, 2))

    sliced = geometry.slice_by_measures(span=crossing)

    assert [(m.region, m.part.length) for m in sliced] == [
        (score.measures[0], Fraction(1, 8)),
        (score.measures[1], Fraction(3, 8)),
    ]


@pytest.mark.unit
def test_a_span_inside_one_measure_is_not_sliced(score: _Score) -> None:
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)
    inside: Span = Span(frame=geometry.root, start=Fraction(9, 8), length=Fraction(1, 8))

    assert [m.region for m in geometry.slice_by_measures(span=inside)] == [score.measures[1]]


@pytest.mark.unit
def test_a_position_past_the_last_measure_belongs_to_no_measure(score: _Score) -> None:
    """Reported as absence so the caller can reject or append a measure — the geometry
    itself has no opinion."""
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)
    beyond: Span = Span(frame=geometry.root, start=Fraction(99), length=Fraction(1, 8))

    assert geometry.measure_at(point=beyond.start_point) is None


@pytest.mark.unit
def test_what_a_new_span_would_displace(score: _Score) -> None:
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)
    over_the_first_beat: Span = Span(
        frame=geometry.root,
        start=Fraction(0),
        length=Fraction(1, 2),
    )

    met = geometry.intersecting(span=over_the_first_beat, scope=score.voice)

    assert [m.region for m in met] == [score.quarter, score.triplet]


@pytest.mark.unit
def test_a_delivered_appended_measure_starts_where_the_score_ended(score: _Score) -> None:
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)
    appended: Measure = Measure.create()

    score.document.append_measure(measure=appended)
    tell_geometry(geometry=geometry, entity=appended)

    assert geometry.of_measure(measure=appended).to_parent.offset == Fraction(3)
    assert len(geometry.measure_regions()) == 4


@pytest.mark.unit
def test_two_documents_never_share_a_timeline(score: _Score) -> None:
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)
    elsewhere: ScoreGeometry = ScoreGeometry(
        document=ScoreDocument.create(
            voices=[Voice()], staffs=[Staff()], measures=[Measure.create()]
        )
    )

    with pytest.raises(UnreachableFrameError):
        geometry.point_of(anchor=score.quarter.anchor).to(frame=elsewhere.root)


@pytest.mark.unit
def test_a_point_cannot_be_placed_in_a_measure_that_does_not_hold_it(score: _Score) -> None:
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)

    with pytest.raises(OutsideFrameError):
        geometry.point_of(anchor=score.quarter.anchor).to(
            frame=geometry.of_measure(measure=score.measures[1])
        )


@pytest.mark.unit
@pytest.mark.parametrize("missing", [0, 1, 2])
def test_a_hole_inside_a_group_moves_no_sibling(score: _Score, missing: int) -> None:
    """A sibling missing in the middle of a gesture — first, middle or last — leaves every
    other leaf where its anchor puts it; nothing is packed into the hole."""
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)
    score.triplet_leaves[missing].detach()

    remaining: list[LeafRhythmicContainer] = [
        leaf for index, leaf in enumerate(score.triplet_leaves) if index != missing
    ]
    expected: list[Fraction] = [
        start
        for index, start in enumerate([Fraction(0), Fraction(1, 8), Fraction(1, 4)])
        if index != missing
    ]

    assert [geometry.span_of(container=leaf).start for leaf in remaining] == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "position",
    [Fraction(1, 8), Fraction(3, 4)],
    ids=["before the group", "past its extent"],
)
def test_a_child_anchored_outside_its_group_has_no_place_in_it(
    score: _Score,
    position: Fraction,
) -> None:
    """An anchor the group's frame does not hold has no coordinate in it, like any point
    outside a frame."""
    score.triplet_leaves[2].detach()
    stray: LeafRhythmicContainer = LeafRhythmicContainer.create(
        parent=score.triplet,
        anchor=TemporalAnchor.create(
            measure=score.measures[0],
            position=MeasurePosition.of_fraction(fraction=position),
        ),
        size=_size(RhythmicValue.EIGHTH),
    )
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)

    with pytest.raises(OutsideFrameError):
        geometry.span_of(container=stray)


@pytest.mark.unit
def test_a_child_anchored_on_the_end_of_its_group_still_has_a_place(score: _Score) -> None:
    """A point on a frame's far boundary belongs to it, so a start there is placed."""
    score.triplet_leaves[2].detach()
    stray: LeafRhythmicContainer = LeafRhythmicContainer.create(
        parent=score.triplet,
        anchor=TemporalAnchor.create(
            measure=score.measures[0],
            position=MeasurePosition.of(numerator=1, denominator=2),
        ),
        size=_size(RhythmicValue.EIGHTH),
    )
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)

    assert geometry.span_of(container=stray).start == Fraction(3, 8)


@pytest.mark.unit
def test_a_group_keeps_its_place_without_its_first_child_or_any_child(score: _Score) -> None:
    """The group starts at its own anchor, so losing children never moves it."""
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)
    before: Span = geometry.span_of(container=score.triplet)

    score.triplet_leaves[0].detach()
    assert geometry.span_of(container=score.triplet) == before

    for leaf in score.triplet_leaves[1:]:
        leaf.detach()
    assert score.triplet.children == []
    assert geometry.span_of(container=score.triplet) == before


@pytest.mark.unit
def test_nested_groups_place_their_children_by_anchor_at_every_depth() -> None:
    """A sixteenth triplet in the room of the first eighth of an eighth triplet: each
    sixteenth sounds 1/36, and each level restates the anchor in its own units."""
    measures: list[Measure] = [Measure.create()]
    voice: Voice = Voice()
    document: ScoreDocument = ScoreDocument.create(
        voices=[voice], staffs=[Staff()], measures=measures
    )
    start: TemporalAnchor = TemporalAnchor.create(
        measure=measures[0], position=MeasurePosition.of(numerator=0, denominator=1)
    )
    outer: GroupRhythmicContainer = GroupRhythmicContainer.create(
        parent=voice,
        anchor=start,
        written_size=_size(RhythmicValue.EIGHTH, 3),
        occupied_size=_size(RhythmicValue.QUARTER),
    )
    inner: GroupRhythmicContainer = GroupRhythmicContainer.create(
        parent=outer,
        anchor=start,
        written_size=_size(RhythmicValue.SIXTEENTH, 3),
        occupied_size=_size(RhythmicValue.EIGHTH),
    )
    sixteenths: list[LeafRhythmicContainer] = [
        LeafRhythmicContainer.create(
            parent=inner,
            anchor=(
                start
                if index == 0
                else TemporalAnchor.create(
                    measure=measures[0],
                    position=MeasurePosition.of_fraction(fraction=Fraction(index, 36)),
                )
            ),
            size=_size(RhythmicValue.SIXTEENTH),
        )
        for index in range(3)
    ]
    geometry: ScoreGeometry = ScoreGeometry(document=document)

    assert [geometry.span_of(container=leaf).start for leaf in sixteenths] == [
        Fraction(0),
        Fraction(1, 16),
        Fraction(1, 8),
    ]
    assert [geometry.global_span_of(container=leaf).start for leaf in sixteenths] == [
        Fraction(0),
        Fraction(1, 36),
        Fraction(1, 18),
    ]
    assert geometry.span_of(container=inner).start == Fraction(0)


@pytest.mark.unit
def test_a_group_crossing_a_barline_places_children_in_both_measures() -> None:
    """A quarter triplet over the barline: its third quarter's anchor lies in the next measure,
    and is still restated in the group's own units."""
    measures: list[Measure] = [Measure.create(), Measure.create()]
    voice: Voice = Voice()
    document: ScoreDocument = ScoreDocument.create(
        voices=[voice], staffs=[Staff()], measures=measures
    )
    anchors: list[TemporalAnchor] = [
        TemporalAnchor.create(
            measure=measures[0], position=MeasurePosition.of(numerator=3, denominator=4)
        ),
        TemporalAnchor.create(
            measure=measures[0], position=MeasurePosition.of(numerator=11, denominator=12)
        ),
        TemporalAnchor.create(
            measure=measures[1], position=MeasurePosition.of(numerator=1, denominator=12)
        ),
    ]
    triplet: GroupRhythmicContainer = GroupRhythmicContainer.create(
        parent=voice,
        anchor=anchors[0],
        written_size=_size(RhythmicValue.QUARTER, 3),
        occupied_size=_size(RhythmicValue.HALF),
    )
    leaves: list[LeafRhythmicContainer] = [
        LeafRhythmicContainer.create(
            parent=triplet, anchor=anchor, size=_size(RhythmicValue.QUARTER)
        )
        for anchor in anchors
    ]
    geometry: ScoreGeometry = ScoreGeometry(document=document)

    assert [geometry.span_of(container=leaf).start for leaf in leaves] == [
        Fraction(0),
        Fraction(1, 4),
        Fraction(1, 2),
    ]
    assert geometry.global_span_of(container=triplet) == Span(
        frame=geometry.root, start=Fraction(3, 4), length=Fraction(1, 2)
    )


@pytest.mark.unit
def test_the_timeline_is_as_long_as_its_measures_and_follows_them(score: _Score) -> None:
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)
    assert geometry.root.extent == Fraction(3)

    appended: Measure = Measure.create()
    score.document.append_measure(measure=appended)
    tell_geometry(geometry=geometry, entity=appended)

    assert geometry.root.extent == Fraction(4)


@pytest.mark.unit
def test_running_past_the_last_measure_is_an_overflow_and_has_no_coordinate(
    score: _Score,
) -> None:
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)
    last_measure = geometry.of_measure(measure=score.measures[2])

    assert overflow(span=Span(frame=geometry.root, start=Fraction(5, 2), length=Fraction(1))) == (
        Fraction(1, 2)
    )
    with pytest.raises(OutsideFrameError):
        Point(frame=last_measure, value=Fraction(5, 4)).to(frame=geometry.root)
