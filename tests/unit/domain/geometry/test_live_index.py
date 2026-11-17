import random
from collections.abc import Callable, Sequence
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
    RhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.geometry import (
    Frame,
    OutsideFrameError,
    Point,
    Span,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.geometry.spaces import SpacesIndex

from ..scene import geometry_differences, size, tell_geometry

# The live index against a geometry built from scratch and against the model read directly.
# Every edit is made on the model, its changed entities delivered to ``invalidate`` before
# the edit or after it, as the contract allows; then every answer must agree with both.

type _Entity = Measure | TemporalAnchor | RhythmicContainer

_THIRTY_SECOND: RhythmicSize = size(RhythmicValue.THIRTY_SECOND)
_SIXTEENTH: RhythmicSize = size(RhythmicValue.SIXTEENTH)
_EIGHTH: RhythmicSize = size(RhythmicValue.EIGHTH)
_QUARTER: RhythmicSize = size(RhythmicValue.QUARTER)
_HALF: RhythmicSize = size(RhythmicValue.HALF)
_EIGHTH_TRIPLET: RhythmicSize = size(RhythmicValue.EIGHTH, count=3)
_DOTTED_QUARTER: RhythmicSize = RhythmicSize(
    value=DottedRhythmicValue(value=RhythmicValue.QUARTER, dots_count=1),
    count=1,
)
_DOTTED_HALF: RhythmicSize = RhythmicSize(
    value=DottedRhythmicValue(value=RhythmicValue.HALF, dots_count=1),
    count=1,
)
_DOTTED_EIGHTH: RhythmicSize = RhythmicSize(
    value=DottedRhythmicValue(value=RhythmicValue.EIGHTH, dots_count=1),
    count=1,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class _Scene:
    """Six measures of 2/4, 4/4, 3/4, 4/4, 4/4 and 2/4 in one voice; barlines at 0, 1/2,
    3/2, 9/4, 13/4, 17/4, the end at 19/4.

    * measure 0: a half;
    * measure 1: a quarter; an eighth triplet on beat 2; on beat 3 an eighth triplet whose
      first eighth is a sixteenth triplet; on beat 4 a quarter triplet crossing the barline
      — a quarter, an eighth, then an eighth on the barline and a quarter in measure 2;
    * measure 2: two quarters after the crossing triplet;
    * measure 3: a half, and a dotted half crossing into measure 4;
    * measure 4: no anchor;
    * measure 5: one anchor holding no container, as a context's anchor does.
    """

    document: ScoreDocument
    voice: Voice
    measures: list[Measure]
    quarter: LeafRhythmicContainer
    triplet: GroupRhythmicContainer
    outer: GroupRhythmicContainer
    inner: GroupRhythmicContainer
    crossing: GroupRhythmicContainer
    crossing_leaves: list[LeafRhythmicContainer]
    quarters: list[LeafRhythmicContainer]
    halves: list[LeafRhythmicContainer]
    orphan: TemporalAnchor


def _anchor(*, measure: Measure, at: Fraction) -> TemporalAnchor:
    """The anchor at a position of the measure, reused when it already exists."""
    existing: TemporalAnchor | None = next(
        (anchor for anchor in measure.anchors if anchor.position.value == at),
        None,
    )
    return existing or TemporalAnchor.create(
        measure=measure,
        position=MeasurePosition.of_fraction(fraction=at),
    )


def _leaf(
    *,
    parent: RhythmicContainerParent,
    measure: Measure,
    at: Fraction,
    leaf_size: RhythmicSize,
) -> LeafRhythmicContainer:
    return LeafRhythmicContainer.create(
        parent=parent,
        anchor=_anchor(measure=measure, at=at),
        size=leaf_size,
    )


def _group(
    *,
    parent: RhythmicContainerParent,
    measure: Measure,
    at: Fraction,
    written: RhythmicSize,
    occupied: RhythmicSize,
) -> GroupRhythmicContainer:
    return GroupRhythmicContainer.create(
        parent=parent,
        anchor=_anchor(measure=measure, at=at),
        written_size=written,
        occupied_size=occupied,
    )


def _build_scene() -> _Scene:
    measures: list[Measure] = [
        Measure.create(time_signature=size(RhythmicValue.QUARTER, count=count))
        for count in (2, 4, 3, 4, 4, 2)
    ]
    voice: Voice = Voice()
    document: ScoreDocument = ScoreDocument.create(
        voices=[voice], staffs=[Staff()], measures=measures
    )
    first: Measure = measures[1]

    _leaf(parent=voice, measure=measures[0], at=Fraction(0), leaf_size=_HALF)
    quarter: LeafRhythmicContainer = _leaf(
        parent=voice, measure=first, at=Fraction(0), leaf_size=_QUARTER
    )

    triplet: GroupRhythmicContainer = _group(
        parent=voice, measure=first, at=Fraction(1, 4), written=_EIGHTH_TRIPLET, occupied=_QUARTER
    )
    for index in range(3):
        _leaf(
            parent=triplet,
            measure=first,
            at=Fraction(1, 4) + Fraction(index, 12),
            leaf_size=_EIGHTH,
        )

    outer: GroupRhythmicContainer = _group(
        parent=voice, measure=first, at=Fraction(1, 2), written=_EIGHTH_TRIPLET, occupied=_QUARTER
    )
    inner: GroupRhythmicContainer = _group(
        parent=outer,
        measure=first,
        at=Fraction(1, 2),
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=_EIGHTH,
    )
    for index in range(3):
        _leaf(
            parent=inner,
            measure=first,
            at=Fraction(1, 2) + Fraction(index, 36),
            leaf_size=_SIXTEENTH,
        )
    for index in (1, 2):
        _leaf(
            parent=outer,
            measure=first,
            at=Fraction(1, 2) + Fraction(index, 12),
            leaf_size=_EIGHTH,
        )

    crossing: GroupRhythmicContainer = _group(
        parent=voice,
        measure=first,
        at=Fraction(3, 4),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=_HALF,
    )
    crossing_leaves: list[LeafRhythmicContainer] = [
        _leaf(parent=crossing, measure=first, at=Fraction(3, 4), leaf_size=_QUARTER),
        _leaf(parent=crossing, measure=first, at=Fraction(11, 12), leaf_size=_EIGHTH),
        _leaf(parent=crossing, measure=measures[2], at=Fraction(0), leaf_size=_EIGHTH),
        _leaf(parent=crossing, measure=measures[2], at=Fraction(1, 12), leaf_size=_QUARTER),
    ]

    quarters: list[LeafRhythmicContainer] = [
        _leaf(parent=voice, measure=measures[2], at=at, leaf_size=_QUARTER)
        for at in (Fraction(1, 4), Fraction(1, 2))
    ]
    halves: list[LeafRhythmicContainer] = [
        _leaf(parent=voice, measure=measures[3], at=Fraction(0), leaf_size=_HALF),
        _leaf(parent=voice, measure=measures[3], at=Fraction(1, 2), leaf_size=_DOTTED_HALF),
    ]
    orphan: TemporalAnchor = _anchor(measure=measures[5], at=Fraction(1, 4))

    return _Scene(
        document=document,
        voice=voice,
        measures=measures,
        quarter=quarter,
        triplet=triplet,
        outer=outer,
        inner=inner,
        crossing=crossing,
        crossing_leaves=crossing_leaves,
        quarters=quarters,
        halves=halves,
        orphan=orphan,
    )


def _warmed(*, scene: _Scene) -> ScoreGeometry:
    """A geometry that has read every fragment, and agrees with a fresh build and the
    model."""
    geometry: ScoreGeometry = ScoreGeometry(document=scene.document)
    assert geometry_differences(geometry=geometry, document=scene.document) == []

    return geometry


def _is_stale(*, geometry: ScoreGeometry, document: ScoreDocument) -> bool:
    """Whether the geometry answers for a score that is no longer there — differently, or
    not at all: a container it never indexed, or one its old numbers place outside its
    group."""
    try:
        return geometry_differences(geometry=geometry, document=document) != []
    except KeyError, OutsideFrameError:
        return True


@dataclass(frozen=True, slots=True, kw_only=True)
class _Courier:
    """Delivers changed entities to the geometry on the chosen side of an edit."""

    geometry: ScoreGeometry
    when: str

    def before(self, *entities: _Entity) -> None:
        if self.when == "before":
            for entity in entities:
                tell_geometry(geometry=self.geometry, entity=entity)

    def after(self, *entities: _Entity) -> None:
        if self.when == "after":
            for entity in entities:
                tell_geometry(geometry=self.geometry, entity=entity)


def _add_anchor(*, courier: _Courier, measure: Measure, at: Fraction) -> TemporalAnchor:
    anchor: TemporalAnchor = TemporalAnchor(
        _position=MeasurePosition.of_fraction(fraction=at),
        _measure=measure,
    )
    courier.before(anchor)
    anchor.attach()
    courier.after(anchor)

    return anchor


def _add_leaf(
    *,
    courier: _Courier,
    parent: RhythmicContainerParent,
    anchor: TemporalAnchor,
    leaf_size: RhythmicSize,
) -> LeafRhythmicContainer:
    leaf: LeafRhythmicContainer = LeafRhythmicContainer(
        written_size=leaf_size,
        occupied_size=leaf_size,
        _parent=parent,
        _anchor=anchor,
    )
    courier.before(leaf)
    leaf.attach()
    courier.after(leaf)

    return leaf


def _delete(*, courier: _Courier, container: RhythmicContainer) -> None:
    courier.before(container)
    container.detach()
    courier.after(container)


def _resize(*, courier: _Courier, leaf: LeafRhythmicContainer, leaf_size: RhythmicSize) -> None:
    courier.before(leaf)
    leaf.set_size(size=leaf_size)
    courier.after(leaf)


def _move(*, courier: _Courier, anchor: TemporalAnchor, measure: Measure, at: Fraction) -> None:
    """Move an anchor; one leaving its measure is delivered after the move whatever the
    side, as the contract requires."""
    leaving: bool = anchor.measure is not measure
    if not leaving:
        courier.before(anchor)

    anchor.move_to(measure=measure, position=MeasurePosition.of_fraction(fraction=at))

    if leaving:
        tell_geometry(geometry=courier.geometry, entity=anchor)
    else:
        courier.after(anchor)


def _set_signature(*, courier: _Courier, measure: Measure, time_signature: RhythmicSize) -> None:
    courier.before(measure)
    measure.set_time_signature(time_signature=time_signature)
    courier.after(measure)


def _split(
    *,
    courier: _Courier,
    group: GroupRhythmicContainer,
    anchor: TemporalAnchor,
    first_written: RhythmicSize,
    first_occupied: RhythmicSize,
    second_written: RhythmicSize,
    second_occupied: RhythmicSize,
) -> None:
    courier.before(group)
    second: GroupRhythmicContainer = group.split_at(
        anchor=anchor,
        first_written_size=first_written,
        first_occupied_size=first_occupied,
        second_written_size=second_written,
        second_occupied_size=second_occupied,
    )
    courier.after(group)
    # a group that did not exist before the edit can only be told after it
    tell_geometry(geometry=courier.geometry, entity=second)


def _place(*, geometry: ScoreGeometry, value: Fraction) -> tuple[Measure, Fraction]:
    """A timeline instant as a measure and a position in it."""
    point: Point = Point(frame=geometry.root, value=value)
    measure: Measure | None = geometry.measure_at(point=point)
    assert measure is not None

    return measure, point.to(frame=geometry.of_measure(measure=measure)).value


def _anchors(*, document: ScoreDocument) -> list[TemporalAnchor]:
    return [anchor for measure in document.measures for anchor in measure.anchors]


def _subtree(*, group: GroupRhythmicContainer) -> list[RhythmicContainer]:
    """The group and every container under it."""
    found: list[RhythmicContainer] = [group]
    pending: list[RhythmicContainer] = list(group.children)
    while pending:
        container: RhythmicContainer = pending.pop()
        found.append(container)
        if isinstance(container, GroupRhythmicContainer):
            pending.extend(container.children)

    return found


def _shift(
    *,
    scene: _Scene,
    courier: _Courier,
    group: GroupRhythmicContainer,
    targets: dict[TemporalAnchor, Fraction],
) -> bool:
    """Move the anchors of a group's content to new timeline instants, in an order no move
    passes another; refused (``False``, nothing changed) unless only the group's content
    starts there, no other anchor lies in the way and all stays before the last measure."""
    geometry: ScoreGeometry = ScoreGeometry(document=scene.document)
    content: list[RhythmicContainer] = _subtree(group=group)
    old: dict[TemporalAnchor, Fraction] = {
        anchor: geometry.point_of(anchor=anchor).value for anchor in targets
    }
    values: list[Fraction] = [*old.values(), *targets.values()]
    last_start: Fraction = geometry.measure_regions()[-1][1].start
    if (
        any(container not in content for anchor in targets for container in anchor.containers)
        or any(
            min(values) <= geometry.point_of(anchor=anchor).value <= max(values)
            for anchor in _anchors(document=scene.document)
            if anchor not in targets
        )
        or min(values) < 0
        or max(values) >= last_start
    ):
        return False

    later: bool = all(targets[anchor] > old[anchor] for anchor in targets)
    for anchor in sorted(targets, key=lambda candidate: old[candidate], reverse=later):
        measure, at = _place(geometry=geometry, value=targets[anchor])
        _move(courier=courier, anchor=anchor, measure=measure, at=at)

    return True


def _rescale(
    *,
    scene: _Scene,
    courier: _Courier,
    group: GroupRhythmicContainer,
    occupied: RhythmicSize,
) -> bool:
    """Give a group another room and re-anchor everything under it to keep its place
    inside, as any change of a group's segment must; ``False`` when that cannot be done."""
    geometry: ScoreGeometry = ScoreGeometry(document=scene.document)
    start: Fraction = geometry.point_of(anchor=group.start_anchor).value
    ratio: Fraction = occupied.fraction / group.occupied_size.fraction
    targets: dict[TemporalAnchor, Fraction] = {}
    for container in _subtree(group=group):
        if container.start_anchor is not group.start_anchor:
            value: Fraction = geometry.point_of(anchor=container.start_anchor).value
            targets[container.start_anchor] = start + (value - start) * ratio

    # the room changes first, so nothing is read before the content follows it
    courier.before(group)
    previous: RhythmicSize = group.occupied_size
    group.occupied_size = occupied
    if targets and not _shift(scene=scene, courier=courier, group=group, targets=targets):
        group.occupied_size = previous
        return False

    courier.after(group)
    return True


# --- each kind of edit, delivered before it and after it -----------------------------------


def _anchor_added(scene: _Scene, courier: _Courier) -> None:
    _add_anchor(courier=courier, measure=scene.measures[1], at=Fraction(1, 8))


def _anchor_moved_within_its_measure(scene: _Scene, courier: _Courier) -> None:
    _move(
        courier=courier,
        anchor=scene.quarters[0].anchor,
        measure=scene.measures[2],
        at=Fraction(3, 8),
    )


def _anchor_moved_to_another_measure(scene: _Scene, courier: _Courier) -> None:
    _move(
        courier=courier,
        anchor=scene.halves[1].anchor,
        measure=scene.measures[4],
        at=Fraction(1, 4),
    )


def _anchor_shared_by_a_group_and_its_first_child_moved(scene: _Scene, courier: _Courier) -> None:
    _move(
        courier=courier,
        anchor=scene.triplet.start_anchor,
        measure=scene.measures[1],
        at=Fraction(1, 4) + Fraction(1, 48),
    )


def _group_child_anchor_moved(scene: _Scene, courier: _Courier) -> None:
    _move(
        courier=courier,
        anchor=scene.triplet.children[2].start_anchor,
        measure=scene.measures[1],
        at=Fraction(5, 12) + Fraction(1, 48),
    )


def _anchor_removed(scene: _Scene, courier: _Courier) -> None:
    courier.before(scene.orphan)
    scene.orphan.detach()
    courier.after(scene.orphan)


def _leaf_created(scene: _Scene, courier: _Courier) -> None:
    anchor: TemporalAnchor = _add_anchor(
        courier=courier, measure=scene.measures[4], at=Fraction(1, 2)
    )
    _add_leaf(courier=courier, parent=scene.voice, anchor=anchor, leaf_size=_QUARTER)


def _leaf_resized(scene: _Scene, courier: _Courier) -> None:
    # the last quarter of the 3/4 measure becomes a half and crosses into the next measure
    _resize(courier=courier, leaf=scene.quarters[1], leaf_size=_HALF)


def _leaf_shrunk_inside_its_measure(scene: _Scene, courier: _Courier) -> None:
    # the dotted half crossing into measure 4 becomes a half ending on the barline
    _resize(courier=courier, leaf=scene.halves[1], leaf_size=_HALF)


def _leaf_in_a_nested_group_resized(scene: _Scene, courier: _Courier) -> None:
    leaf: RhythmicContainer = scene.inner.children[2]
    assert isinstance(leaf, LeafRhythmicContainer)
    _resize(courier=courier, leaf=leaf, leaf_size=_THIRTY_SECOND)


def _leaf_deleted(scene: _Scene, courier: _Courier) -> None:
    _delete(courier=courier, container=scene.quarters[0])


def _group_created(scene: _Scene, courier: _Courier) -> None:
    anchor: TemporalAnchor = _add_anchor(
        courier=courier, measure=scene.measures[4], at=Fraction(1, 4)
    )
    group: GroupRhythmicContainer = GroupRhythmicContainer(
        written_size=_EIGHTH_TRIPLET,
        occupied_size=_QUARTER,
        _parent=scene.voice,
        _anchor=anchor,
    )
    courier.before(group)
    group.attach()
    courier.after(group)


def _group_deleted(scene: _Scene, courier: _Courier) -> None:
    for child in list(scene.triplet.children):
        _delete(courier=courier, container=child)
    _delete(courier=courier, container=scene.triplet)


def _group_split(scene: _Scene, courier: _Courier) -> None:
    _split(
        courier=courier,
        group=scene.crossing,
        anchor=scene.crossing_leaves[2].anchor,
        first_written=_EIGHTH_TRIPLET,
        first_occupied=_QUARTER,
        second_written=_EIGHTH_TRIPLET,
        second_occupied=_QUARTER,
    )


def _nested_group_resized(scene: _Scene, courier: _Courier) -> None:
    # three eighths in the room of a dotted eighth: the nested triplet and every leaf under
    # it last half as long, and are re-anchored to keep their places
    assert _rescale(scene=scene, courier=courier, group=scene.outer, occupied=_DOTTED_EIGHTH)


def _crossing_tuplet_rescaled(scene: _Scene, courier: _Courier) -> None:
    # three quarters in a dotted quarter: the tail moves back over the barline
    assert _rescale(scene=scene, courier=courier, group=scene.crossing, occupied=_DOTTED_QUARTER)


def _measure_inserted(scene: _Scene, courier: _Courier) -> None:
    measure: Measure = Measure.create(time_signature=size(RhythmicValue.QUARTER, count=5))
    courier.before(measure)
    scene.document.insert_measure_after(measure=measure, after=scene.measures[2])
    courier.after(measure)


def _measure_appended(scene: _Scene, courier: _Courier) -> None:
    measure: Measure = Measure.create()
    courier.before(measure)
    scene.document.append_measure(measure=measure)
    courier.after(measure)


def _measure_removed(scene: _Scene, courier: _Courier) -> None:
    courier.before(scene.measures[4])
    scene.document.remove_measure(measure=scene.measures[4])
    courier.after(scene.measures[4])


def _measure_inserted_before_the_first(scene: _Scene, courier: _Courier) -> None:
    measure: Measure = Measure.create()
    courier.before(measure)
    scene.document.insert_measure_before(measure=measure, before=scene.measures[0])
    courier.after(measure)


def _first_measure_removed(scene: _Scene, courier: _Courier) -> None:
    # emptied first, as the engine does: what is anchored in a removed measure has no place
    # on the timeline
    half: RhythmicContainer = scene.voice.children[0]
    anchor: TemporalAnchor = half.start_anchor
    _delete(courier=courier, container=half)
    courier.before(anchor)
    anchor.detach()
    courier.after(anchor)

    courier.before(scene.measures[0])
    scene.document.remove_measure(measure=scene.measures[0])
    courier.after(scene.measures[0])


def _signature_before_the_crossing_tuplet(scene: _Scene, courier: _Courier) -> None:
    # the measure before shifts the tuplet and every child of it alike
    _set_signature(
        courier=courier,
        measure=scene.measures[0],
        time_signature=size(RhythmicValue.QUARTER, count=3),
    )


def _signature_after_the_crossing_tuplet(scene: _Scene, courier: _Courier) -> None:
    _set_signature(
        courier=courier,
        measure=scene.measures[3],
        time_signature=size(RhythmicValue.QUARTER, count=5),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class _Edit:
    apply: Callable[[_Scene, _Courier], None]
    # whether a geometry told nothing answers for the old score — false where every answer
    # the edit changes is read live
    shows: bool = True
    # an anchor leaving its measure is always delivered after the move
    whens: tuple[str, ...] = ("before", "after")


_EDITS: dict[str, _Edit] = {
    "anchor added": _Edit(apply=_anchor_added, shows=False),
    "anchor moved within its measure": _Edit(apply=_anchor_moved_within_its_measure, shows=False),
    "anchor moved to another measure": _Edit(
        apply=_anchor_moved_to_another_measure, whens=("after",)
    ),
    "anchor shared by a group and its first child moved": _Edit(
        apply=_anchor_shared_by_a_group_and_its_first_child_moved, shows=False
    ),
    "group child's anchor moved": _Edit(apply=_group_child_anchor_moved, shows=False),
    "anchor removed": _Edit(apply=_anchor_removed, shows=False),
    "leaf created": _Edit(apply=_leaf_created),
    "leaf resized": _Edit(apply=_leaf_resized),
    "leaf shrunk inside its measure": _Edit(apply=_leaf_shrunk_inside_its_measure),
    # a span's length is read live, and the leaf stays inside its measure
    "leaf in a nested group resized": _Edit(apply=_leaf_in_a_nested_group_resized, shows=False),
    "leaf deleted": _Edit(apply=_leaf_deleted),
    "group created": _Edit(apply=_group_created),
    "group deleted": _Edit(apply=_group_deleted),
    "group split at a barline": _Edit(apply=_group_split),
    # re-anchored content keeps its offsets inside, so old offsets still read right
    "nested group resized": _Edit(apply=_nested_group_resized),
    "crossing tuplet rescaled": _Edit(apply=_crossing_tuplet_rescaled),
    "measure inserted in the middle": _Edit(apply=_measure_inserted),
    "measure appended": _Edit(apply=_measure_appended),
    "measure removed in the middle": _Edit(apply=_measure_removed),
    "measure inserted before the first": _Edit(apply=_measure_inserted_before_the_first),
    "first measure removed": _Edit(apply=_first_measure_removed),
    "time signature before the crossing tuplet": _Edit(apply=_signature_before_the_crossing_tuplet),
    "time signature after the crossing tuplet": _Edit(apply=_signature_after_the_crossing_tuplet),
}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "when"),
    [(name, when) for name, edit in _EDITS.items() for when in edit.whens],
)
def test_an_edit_delivered_heals_to_a_fresh_build(name: str, when: str) -> None:
    edit: _Edit = _EDITS[name]
    scene: _Scene = _build_scene()
    healed: ScoreGeometry = _warmed(scene=scene)
    untold: ScoreGeometry = _warmed(scene=scene)

    edit.apply(scene, _Courier(geometry=healed, when=when))

    assert geometry_differences(geometry=healed, document=scene.document) == []
    assert _is_stale(geometry=untold, document=scene.document) is edit.shows


# --- the index itself ------------------------------------------------------------------------


@pytest.mark.unit
def test_a_geometry_read_in_any_order_answers_as_a_fresh_build() -> None:
    """Measures of different signatures, nested tuplets and a tuplet over a barline, read
    from the end backwards first."""
    scene: _Scene = _build_scene()
    geometry: ScoreGeometry = ScoreGeometry(document=scene.document)

    for measure in reversed(scene.measures):
        geometry.contents_in(scope=scene.voice, measure=measure)
    for leaf in reversed(scene.crossing_leaves):
        geometry.global_span_of(container=leaf)

    assert geometry_differences(geometry=geometry, document=scene.document) == []


@pytest.mark.unit
def test_a_single_span_reads_only_its_own_measure() -> None:
    """Built lazily: answering for a container of one measure leaves every other measure
    unread, so an edit there before it is read is seen without being delivered."""
    scene: _Scene = _build_scene()
    geometry: ScoreGeometry = ScoreGeometry(document=scene.document)
    geometry.span_of(container=scene.quarter)

    scene.halves[1].anchor.move_to(
        measure=scene.measures[3],
        position=MeasurePosition.of(numerator=5, denominator=8),
    )

    assert geometry.span_of(container=scene.halves[1]).start == Fraction(9, 4) + Fraction(5, 8)


@pytest.mark.unit
def test_telling_about_one_leaf_heals_only_that_leaf() -> None:
    """The index heals by child: two leaves of the voice resized, one delivered — the voice
    reads right for it and still wrong for the other, until that one is delivered too."""
    scene: _Scene = _build_scene()
    geometry: ScoreGeometry = _warmed(scene=scene)

    scene.quarters[0].set_size(size=_EIGHTH)
    scene.halves[1].set_size(size=_QUARTER)
    tell_geometry(geometry=geometry, entity=scene.quarters[0])

    assert geometry.span_of(container=scene.quarters[0]).length == Fraction(1, 8)
    assert _is_stale(geometry=geometry, document=scene.document)

    tell_geometry(geometry=geometry, entity=scene.halves[1])

    assert geometry_differences(geometry=geometry, document=scene.document) == []


@pytest.mark.unit
def test_an_edit_reads_the_reach_of_the_touched_child_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A voice of many children heals one resized leaf by reading that leaf's reach alone,
    not the reach of every child again."""
    scene: _Scene = _build_scene()
    geometry: ScoreGeometry = _warmed(scene=scene)
    reads: list[Measure] = []
    original: Callable[..., Sequence[Measure]] = SpacesIndex.measures_from

    def counting(self: SpacesIndex, *, measure: Measure, end: Fraction) -> Sequence[Measure]:
        reads.append(measure)
        return original(self, measure=measure, end=end)

    monkeypatch.setattr(SpacesIndex, "measures_from", counting)

    scene.halves[1].set_size(size=_QUARTER)
    tell_geometry(geometry=geometry, entity=scene.halves[1])
    geometry.contents_in(scope=scene.voice, measure=scene.measures[3])

    assert reads == [scene.halves[1].start_anchor.measure]


@pytest.mark.unit
def test_a_leaf_inserted_between_two_others_is_listed_between_them() -> None:
    scene: _Scene = _build_scene()
    geometry: ScoreGeometry = _warmed(scene=scene)
    measure: Measure = scene.measures[4]
    anchor: TemporalAnchor = _add_anchor(
        courier=_Courier(geometry=geometry, when="after"), measure=measure, at=Fraction(1, 4)
    )

    leaf: LeafRhythmicContainer = _add_leaf(
        courier=_Courier(geometry=geometry, when="after"),
        parent=scene.voice,
        anchor=anchor,
        leaf_size=_QUARTER,
    )

    listed: list[RhythmicContainer] = [
        child for child, _ in geometry.contents_in(scope=scene.voice, measure=measure)
    ]
    assert leaf in listed
    assert geometry_differences(geometry=geometry, document=scene.document) == []


@pytest.mark.unit
def test_a_child_taken_out_of_the_scope_is_listed_nowhere() -> None:
    scene: _Scene = _build_scene()
    geometry: ScoreGeometry = _warmed(scene=scene)
    crossing: LeafRhythmicContainer = scene.halves[1]
    reached: list[Measure] = [
        measure
        for measure in scene.measures
        if crossing
        in [child for child, _ in geometry.contents_in(scope=scene.voice, measure=measure)]
    ]
    assert len(reached) == 2

    _delete(courier=_Courier(geometry=geometry, when="after"), container=crossing)

    for measure in reached:
        assert crossing not in [
            child for child, _ in geometry.contents_in(scope=scene.voice, measure=measure)
        ]
    assert geometry_differences(geometry=geometry, document=scene.document) == []


@pytest.mark.unit
def test_reading_after_an_edit_without_delivering_it_may_be_stale() -> None:
    """The contract: the index heals only what it is told about, and the comparison sees
    the difference."""
    scene: _Scene = _build_scene()
    geometry: ScoreGeometry = _warmed(scene=scene)

    scene.halves[1].set_size(size=_QUARTER)

    assert geometry_differences(geometry=geometry, document=scene.document) != []


@pytest.mark.unit
def test_a_container_created_without_delivery_is_read_where_it_lies() -> None:
    """A container created after its parent was read answers from its own anchor, not from a
    guess: the answer equals a fresh build's."""
    scene: _Scene = _build_scene()
    geometry: ScoreGeometry = ScoreGeometry(document=scene.document)
    geometry.span_of(container=scene.quarter)

    created: LeafRhythmicContainer = _leaf(
        parent=scene.voice, measure=scene.measures[1], at=Fraction(1, 8), leaf_size=_EIGHTH
    )

    fresh: ScoreGeometry = ScoreGeometry(document=scene.document)
    assert geometry.span_of(container=created) == fresh.span_of(container=created)


# --- contents_in ---------------------------------------------------------------------------


def _children(entries: list[tuple[RhythmicContainer, Span]]) -> list[RhythmicContainer]:
    return [child for child, _ in entries]


def _reaching(
    *,
    geometry: ScoreGeometry,
    scope: RhythmicContainerParent,
    measure: Measure,
) -> list[tuple[RhythmicContainer, Span]]:
    """``contents_of`` filtered by the measure's region — what ``contents_in`` must equal."""
    region: Span = next(
        span for candidate, span in geometry.measure_regions() if candidate is measure
    )

    return [
        (child, span)
        for child, span in geometry.contents_of(scope=scope)
        if geometry.global_span_of(container=child).intersects(region)
    ]


@pytest.mark.unit
def test_contents_in_lists_what_reaches_into_each_measure() -> None:
    scene: _Scene = _build_scene()
    geometry: ScoreGeometry = ScoreGeometry(document=scene.document)

    for scope in (scene.voice, scene.triplet, scene.outer, scene.inner, scene.crossing):
        for measure in scene.measures:
            assert geometry.contents_in(scope=scope, measure=measure) == _reaching(
                geometry=geometry, scope=scope, measure=measure
            )


@pytest.mark.unit
def test_a_child_crossing_a_barline_is_listed_in_both_measures() -> None:
    scene: _Scene = _build_scene()
    geometry: ScoreGeometry = ScoreGeometry(document=scene.document)

    assert scene.crossing in _children(
        geometry.contents_in(scope=scene.voice, measure=scene.measures[1])
    )
    assert scene.crossing in _children(
        geometry.contents_in(scope=scene.voice, measure=scene.measures[2])
    )
    assert _children(geometry.contents_in(scope=scene.voice, measure=scene.measures[4])) == [
        scene.halves[1]
    ]
    # inside the group, in its own frame: two children before the barline, two after
    assert geometry.contents_in(scope=scene.crossing, measure=scene.measures[1]) == [
        (leaf, geometry.span_of(container=leaf)) for leaf in scene.crossing_leaves[:2]
    ]
    assert geometry.contents_in(scope=scene.crossing, measure=scene.measures[2]) == [
        (leaf, geometry.span_of(container=leaf)) for leaf in scene.crossing_leaves[2:]
    ]


@pytest.mark.unit
def test_a_child_ending_on_a_barline_is_not_listed_after_it() -> None:
    scene: _Scene = _build_scene()
    geometry: ScoreGeometry = ScoreGeometry(document=scene.document)

    # the second quarter of the 3/4 measure ends on its barline
    assert scene.quarters[1] in _children(
        geometry.contents_in(scope=scene.voice, measure=scene.measures[2])
    )
    assert _children(geometry.contents_in(scope=scene.voice, measure=scene.measures[3])) == (
        scene.halves
    )


@pytest.mark.unit
def test_an_empty_measure_has_no_contents() -> None:
    scene: _Scene = _build_scene()
    geometry: ScoreGeometry = ScoreGeometry(document=scene.document)

    assert geometry.contents_in(scope=scene.voice, measure=scene.measures[5]) == []
    assert geometry.contents_in(scope=scene.triplet, measure=scene.measures[0]) == []


@pytest.mark.unit
def test_contents_in_follows_the_order_of_the_scope() -> None:
    scene: _Scene = _build_scene()
    geometry: ScoreGeometry = ScoreGeometry(document=scene.document)

    assert _children(geometry.contents_in(scope=scene.voice, measure=scene.measures[1])) == [
        scene.quarter,
        scene.triplet,
        scene.outer,
        scene.crossing,
    ]
    assert _children(geometry.contents_in(scope=scene.outer, measure=scene.measures[1])) == list(
        scene.outer.children
    )


# --- measure_at ----------------------------------------------------------------------------


@pytest.mark.unit
def test_measure_at_finds_the_measure_on_and_around_every_barline() -> None:
    """A barline belongs to the measure starting there, the end to none."""
    scene: _Scene = _build_scene()
    geometry: ScoreGeometry = ScoreGeometry(document=scene.document)
    just_before: Fraction = Fraction(1, 10**6)
    barlines: list[Fraction] = [
        Fraction(0),
        Fraction(1, 2),
        Fraction(3, 2),
        Fraction(9, 4),
        Fraction(13, 4),
        Fraction(17, 4),
    ]

    for index, barline in enumerate(barlines):
        assert (
            geometry.measure_at(point=Point(frame=geometry.root, value=barline))
            is (scene.measures[index])
        )
        if index > 0:
            assert (
                geometry.measure_at(point=Point(frame=geometry.root, value=barline - just_before))
                is (scene.measures[index - 1])
            )

    end: Fraction = Fraction(19, 4)
    assert (
        geometry.measure_at(point=Point(frame=geometry.root, value=end - just_before))
        is (scene.measures[5])
    )
    assert geometry.measure_at(point=Point(frame=geometry.root, value=end)) is None
    assert geometry.measure_at(point=Point(frame=geometry.root, value=end + 1)) is None


# --- a long run of random edits ------------------------------------------------------------

_SIGNATURES: list[RhythmicSize] = [
    size(RhythmicValue.QUARTER, count=count) for count in (2, 3, 4, 5)
]
_LEAF_SIZES: list[RhythmicSize] = [_THIRTY_SECOND, _SIXTEENTH, _EIGHTH, _QUARTER, _HALF]
# a grid fine enough to find room between any two anchors the run makes
_STEP: Fraction = Fraction(1, 96)


@dataclass(frozen=True, slots=True, kw_only=True)
class _Run:
    """One random edit's context: the score, a fresh geometry to choose by (never the one
    under test) and the delivery side."""

    scene: _Scene
    geometry: ScoreGeometry
    courier: _Courier
    rng: random.Random

    @property
    def groups(self) -> list[GroupRhythmicContainer]:
        found: list[GroupRhythmicContainer] = []
        pending: list[RhythmicContainer] = list(self.scene.voice.children)
        while pending:
            container: RhythmicContainer = pending.pop()
            if isinstance(container, GroupRhythmicContainer):
                found.append(container)
                pending.extend(container.children)

        return found

    @property
    def last_start(self) -> Fraction:
        """Where the last measure begins: content stays before it, so nothing runs past
        the end."""
        return self.geometry.measure_regions()[-1][1].start

    def instant(self, *, anchor: TemporalAnchor) -> Fraction:
        return self.geometry.point_of(anchor=anchor).value

    def neighbours(self, *, anchor: TemporalAnchor) -> tuple[Fraction, Fraction]:
        """The instants of the anchors before and after it on the timeline."""
        instants: list[Fraction] = sorted(
            self.instant(anchor=other) for other in _anchors(document=self.scene.document)
        )
        index: int = instants.index(self.instant(anchor=anchor))
        before: Fraction = instants[index - 1] if index > 0 else Fraction(-1)
        after: Fraction = instants[index + 1] if index + 1 < len(instants) else self.last_start

        return before, min(after, self.last_start)

    def crossed(self, *, barline: Fraction) -> bool:
        """Whether a group reaches over the barline, so moving it would tear the group."""
        for group in self.groups:
            reach: Span = self.geometry.global_span_of(container=group)
            if reach.start < barline < reach.end:
                return True

        return False

    def in_a_group(self, *, value: Fraction) -> bool:
        for group in self.groups:
            reach: Span = self.geometry.global_span_of(container=group)
            if reach.start <= value < reach.end:
                return True

        return False

    def group_leaves(self) -> list[tuple[GroupRhythmicContainer, LeafRhythmicContainer]]:
        return [
            (group, child)
            for group in self.groups
            for child in group.children
            if isinstance(child, LeafRhythmicContainer)
        ]

    def room_in(
        self,
        *,
        group: GroupRhythmicContainer,
        child: RhythmicContainer,
    ) -> tuple[Fraction, Fraction]:
        """The free stretch of the group's frame around a child: from the end of the
        siblings before it to the start of the first after it."""
        start: Fraction = self.geometry.span_of(container=child).start
        low: Fraction = Fraction(0)
        high: Fraction = group.written_size.fraction
        for sibling, span in self.geometry.contents_of(scope=group):
            if sibling is child:
                continue
            if span.start < start:
                low = max(low, span.end)
            else:
                high = min(high, span.start)

        return low, high


def _spell(*, length: Fraction) -> RhythmicSize | None:
    """A length as a count of the longest plain value dividing it."""
    for rhythmic_value in RhythmicValue:
        count: Fraction = length / rhythmic_value.fraction
        if count > 0 and count.denominator == 1:
            return RhythmicSize(value=DottedRhythmicValue(value=rhythmic_value), count=int(count))

    return None


def _add_voice_leaf(run: _Run) -> bool:
    measure: Measure = run.rng.choice(list(run.scene.document.measures)[:-1])
    region: Span = next(
        span for candidate, span in run.geometry.measure_regions() if candidate is measure
    )
    taken: set[Fraction] = {
        run.instant(anchor=anchor) for anchor in _anchors(document=run.scene.document)
    }
    free: list[Fraction] = [
        region.start + Fraction(index, 8)
        for index in range(int(region.length * 8))
        if region.start + Fraction(index, 8) not in taken
        and not run.in_a_group(value=region.start + Fraction(index, 8))
    ]
    if not free:
        return False

    at: Fraction = run.rng.choice(free) - region.start
    anchor: TemporalAnchor = _add_anchor(courier=run.courier, measure=measure, at=at)
    _add_leaf(courier=run.courier, parent=run.scene.voice, anchor=anchor, leaf_size=_EIGHTH)
    return True


def _voice_leaves(run: _Run) -> list[LeafRhythmicContainer]:
    return [child for child in run.scene.voice.children if isinstance(child, LeafRhythmicContainer)]


def _resize_voice_leaf(run: _Run) -> bool:
    leaves: list[LeafRhythmicContainer] = _voice_leaves(run)
    if not leaves:
        return False

    leaf: LeafRhythmicContainer = run.rng.choice(leaves)
    sizes: list[RhythmicSize] = [
        candidate for candidate in (_EIGHTH, _QUARTER, _HALF) if candidate != leaf.written_size
    ]
    _resize(courier=run.courier, leaf=leaf, leaf_size=run.rng.choice(sizes))
    return True


def _move_voice_leaf(run: _Run) -> bool:
    movable: list[TemporalAnchor] = [
        leaf.anchor
        for leaf in _voice_leaves(run)
        if all(
            isinstance(container, LeafRhythmicContainer) and container.parent is run.scene.voice
            for container in leaf.anchor.containers
        )
    ]
    if not movable:
        return False

    anchor: TemporalAnchor = run.rng.choice(movable)
    before, after = run.neighbours(anchor=anchor)
    current: Fraction = run.instant(anchor=anchor)
    targets: list[Fraction] = [
        value
        for value in (before + _STEP * index for index in range(1, int((after - before) / _STEP)))
        if before < value < after
        and value != current
        and value >= 0
        and not run.in_a_group(value=value)
    ]
    if not targets:
        return False

    measure, at = _place(geometry=run.geometry, value=run.rng.choice(targets))
    _move(courier=run.courier, anchor=anchor, measure=measure, at=at)
    return True


def _delete_voice_leaf(run: _Run) -> bool:
    leaves: list[LeafRhythmicContainer] = _voice_leaves(run)
    if not leaves:
        return False

    _delete(courier=run.courier, container=run.rng.choice(leaves))
    return True


def _insert_measure(run: _Run) -> bool:
    measures: list[Measure] = list(run.scene.document.measures)
    after: Measure = run.rng.choice(measures)
    if run.crossed(barline=run.geometry.measure_regions()[measures.index(after)][1].end):
        return False

    inserted: Measure = Measure.create(time_signature=run.rng.choice(_SIGNATURES))
    run.courier.before(inserted)
    run.scene.document.insert_measure_after(measure=inserted, after=after)
    run.courier.after(inserted)
    return True


def _remove_measure(run: _Run) -> bool:
    regions: list[tuple[Measure, Span]] = run.geometry.measure_regions()
    empty: list[Measure] = [
        measure
        for measure, region in regions[1:-1]
        if not measure.anchors and not run.crossed(barline=region.end)
    ]
    if not empty:
        return False

    removed: Measure = run.rng.choice(empty)
    run.courier.before(removed)
    run.scene.document.remove_measure(measure=removed)
    run.courier.after(removed)
    return True


def _change_signature(run: _Run) -> bool:
    measure, region = run.rng.choice(run.geometry.measure_regions())
    signatures: list[RhythmicSize] = [
        candidate
        for candidate in _SIGNATURES
        if candidate != measure.time_signature
        and all(anchor.position.value < candidate.fraction for anchor in measure.anchors)
    ]
    if run.crossed(barline=region.end) or not signatures:
        return False

    _set_signature(courier=run.courier, measure=measure, time_signature=run.rng.choice(signatures))
    return True


def _add_group_child(run: _Run) -> bool:
    groups: list[GroupRhythmicContainer] = run.groups
    if not groups:
        return False

    group: GroupRhythmicContainer = run.rng.choice(groups)
    covered: list[Span] = sorted(
        (span for _, span in run.geometry.contents_of(scope=group)),
        key=lambda span: span.start,
    )
    room: list[tuple[Fraction, Fraction]] = []
    cursor: Fraction = Fraction(0)
    for span in covered:
        if span.start > cursor:
            room.append((cursor, span.start))
        cursor = max(cursor, span.end)
    if cursor < group.written_size.fraction:
        room.append((cursor, group.written_size.fraction))

    used: Fraction = sum((child.occupied_size.fraction for child in group.children), Fraction(0))
    if not room:
        return False

    low, high = run.rng.choice(room)
    sizes: list[RhythmicSize] = [
        candidate
        for candidate in _LEAF_SIZES
        if candidate.fraction <= high - low
        and used + candidate.fraction <= group.written_size.fraction
    ]
    if not sizes:
        return False

    value: Fraction = (
        Point(frame=run.geometry.of_group(group=group), value=low).to(frame=run.geometry.root).value
    )
    measure, at = _place(geometry=run.geometry, value=value)
    existing: TemporalAnchor | None = next(
        (anchor for anchor in measure.anchors if anchor.position.value == at),
        None,
    )
    anchor: TemporalAnchor = existing or _add_anchor(courier=run.courier, measure=measure, at=at)
    _add_leaf(courier=run.courier, parent=group, anchor=anchor, leaf_size=run.rng.choice(sizes))
    return True


def _delete_group_child(run: _Run) -> bool:
    pairs: list[tuple[GroupRhythmicContainer, LeafRhythmicContainer]] = run.group_leaves()
    if not pairs:
        return False

    _, leaf = run.rng.choice(pairs)
    _delete(courier=run.courier, container=leaf)
    return True


def _resize_group_child(run: _Run) -> bool:
    pairs: list[tuple[GroupRhythmicContainer, LeafRhythmicContainer]] = run.group_leaves()
    if not pairs:
        return False

    group, leaf = run.rng.choice(pairs)
    start: Fraction = run.geometry.span_of(container=leaf).start
    _, high = run.room_in(group=group, child=leaf)
    sizes: list[RhythmicSize] = [
        candidate
        for candidate in _LEAF_SIZES
        if candidate != leaf.written_size and candidate.fraction <= high - start
    ]
    if not sizes:
        return False

    _resize(courier=run.courier, leaf=leaf, leaf_size=run.rng.choice(sizes))
    return True


def _move_group_child(run: _Run) -> bool:
    pairs: list[tuple[GroupRhythmicContainer, LeafRhythmicContainer]] = [
        (group, leaf) for group, leaf in run.group_leaves() if leaf.anchor.containers == [leaf]
    ]
    if not pairs:
        return False

    group, leaf = run.rng.choice(pairs)
    low, high = run.room_in(group=group, child=leaf)
    current: Fraction = run.geometry.span_of(container=leaf).start
    before, after = run.neighbours(anchor=leaf.anchor)
    frame: Frame = run.geometry.of_group(group=group)
    targets: list[Fraction] = []
    offset: Fraction = low
    while offset + leaf.occupied_size.fraction <= high:
        value: Fraction = Point(frame=frame, value=offset).to(frame=run.geometry.root).value
        if offset != current and before < value < after:
            targets.append(value)
        offset += _STEP

    if not targets:
        return False

    measure, at = _place(geometry=run.geometry, value=run.rng.choice(targets))
    _move(courier=run.courier, anchor=leaf.anchor, measure=measure, at=at)
    return True


def _move_group(run: _Run) -> bool:
    groups: list[GroupRhythmicContainer] = run.groups
    if not groups:
        return False

    group: GroupRhythmicContainer = run.rng.choice(groups)
    delta: Fraction = run.rng.choice((Fraction(-1, 24), Fraction(-1, 48), Fraction(1, 48)))
    targets: dict[TemporalAnchor, Fraction] = {
        container.start_anchor: run.instant(anchor=container.start_anchor) + delta
        for container in _subtree(group=group)
    }
    return _shift(scene=run.scene, courier=run.courier, group=group, targets=targets)


def _split_group(run: _Run) -> bool:
    groups: list[GroupRhythmicContainer] = run.groups
    if not groups:
        return False

    group: GroupRhythmicContainer = run.rng.choice(groups)
    written: Fraction = group.written_size.fraction
    occupied: Fraction = group.occupied_size.fraction
    inside: list[tuple[TemporalAnchor, Fraction]] = [
        (child.start_anchor, span.start)
        for child, span in run.geometry.contents_of(scope=group)
        if 0 < span.start < written and child.start_anchor is not group.start_anchor
    ]
    if not inside:
        return False

    anchor, first = run.rng.choice(inside)
    spelled: list[RhythmicSize] = []
    for length in (first, written - first):
        for part in (length, length * occupied / written):
            part_size: RhythmicSize | None = _spell(length=part)
            if part_size is None:
                return False
            spelled.append(part_size)

    try:
        _split(
            courier=run.courier,
            group=group,
            anchor=anchor,
            first_written=spelled[0],
            first_occupied=spelled[1],
            second_written=spelled[2],
            second_occupied=spelled[3],
        )
    except ValueError:
        return False

    return True


def _rescale_group(run: _Run) -> bool:
    groups: list[GroupRhythmicContainer] = run.groups
    if not groups:
        return False

    group: GroupRhythmicContainer = run.rng.choice(groups)
    written: Fraction = group.written_size.fraction
    sizes: list[RhythmicSize] = []
    for ratio in (Fraction(1, 2), Fraction(2, 3), Fraction(3, 4)):
        spelled: RhythmicSize | None = _spell(length=written * ratio)
        if spelled is not None and spelled.fraction != group.occupied_size.fraction:
            sizes.append(spelled)
    if not sizes:
        return False

    return _rescale(
        scene=run.scene,
        courier=run.courier,
        group=group,
        occupied=run.rng.choice(sizes),
    )


_KINDS: list[Callable[[_Run], bool]] = [
    _add_voice_leaf,
    _resize_voice_leaf,
    _move_voice_leaf,
    _delete_voice_leaf,
    _insert_measure,
    _remove_measure,
    _change_signature,
    _add_group_child,
    _delete_group_child,
    _resize_group_child,
    _move_group_child,
    _move_group,
    _split_group,
    _rescale_group,
]


@pytest.mark.unit
@pytest.mark.parametrize("seed", [20261021, 7, 1234])
def test_a_long_run_of_random_edits_heals_after_every_step(seed: int) -> None:
    """Random edits of every kind, each delivered on a side the contract allows and
    compared after every step; most of them must actually change the score."""
    scene: _Scene = _build_scene()
    geometry: ScoreGeometry = ScoreGeometry(document=scene.document)
    rng: random.Random = random.Random(seed)

    effective: int = 0
    for step in range(80):
        run: _Run = _Run(
            scene=scene,
            geometry=ScoreGeometry(document=scene.document),
            courier=_Courier(geometry=geometry, when=rng.choice(("before", "after"))),
            rng=rng,
        )
        if rng.choice(_KINDS)(run):
            effective += 1

        assert geometry_differences(geometry=geometry, document=scene.document) == [], step

    assert effective >= 60
