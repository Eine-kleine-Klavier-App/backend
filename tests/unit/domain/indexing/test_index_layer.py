from fractions import Fraction

from piano_app.domain.score.document.models.context import ClefChange, Context, DynamicChange
from piano_app.domain.score.document.models.notation import DynamicMarking, RhythmicValue
from piano_app.domain.score.document.models.structural import Staff, TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.indexing import Index, IndexLayer

from ..scene import Score, build_score, eighth_triplet, note


class _Recorder(Index):
    """Writes down which event it was told of, and about what."""

    def __init__(self, *, name: str, told: list[tuple[str, str, object]]) -> None:
        self._name: str = name
        self._told: list[tuple[str, str, object]] = told

    def invalidate_measures(self) -> None:
        self._told.append((self._name, "measures", None))

    def invalidate_anchor(self, *, anchor: TemporalAnchor) -> None:
        self._told.append((self._name, "anchor", anchor))

    def invalidate_leaf(self, *, leaf: LeafRhythmicContainer) -> None:
        self._told.append((self._name, "leaf", leaf))

    def invalidate_group(self, *, group: GroupRhythmicContainer) -> None:
        self._told.append((self._name, "group", group))

    def invalidate_scope(self, *, scope: RhythmicContainerParent) -> None:
        self._told.append((self._name, "scope", scope))

    def invalidate_staff(self, *, staff: Staff) -> None:
        self._told.append((self._name, "staff", staff))

    def invalidate_context(self, *, context: Context) -> None:
        self._told.append((self._name, "context", context))


def _layer(*, told: list[tuple[str, str, object]]) -> IndexLayer:
    """A layer over two recorders and, between them, an index that answers for nothing."""
    return IndexLayer(
        indexes=(
            _Recorder(name="first", told=told),
            Index(),
            _Recorder(name="second", told=told),
        )
    )


def test_every_event_goes_to_every_index_in_the_order_they_were_given() -> None:
    score: Score = build_score(measure_count=1)
    leaf: LeafRhythmicContainer = note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.QUARTER,
        step=1,
    )
    group: GroupRhythmicContainer = eighth_triplet(
        score=score, parent=score.voice, at=Fraction(1, 4)
    )
    context: Context = score.staff.contexts[0]
    told: list[tuple[str, str, object]] = []
    layer: IndexLayer = _layer(told=told)

    layer.invalidate_measures()
    layer.invalidate_anchor(anchor=leaf.anchor)
    layer.invalidate_leaf(leaf=leaf)
    layer.invalidate_group(group=group)
    layer.invalidate_scope(scope=score.voice)
    layer.invalidate_staff(staff=score.staff)
    layer.invalidate_context(context=context)

    assert told == [
        ("first", "measures", None),
        ("second", "measures", None),
        ("first", "anchor", leaf.anchor),
        ("second", "anchor", leaf.anchor),
        ("first", "leaf", leaf),
        ("second", "leaf", leaf),
        ("first", "group", group),
        ("second", "group", group),
        ("first", "scope", score.voice),
        ("second", "scope", score.voice),
        ("first", "staff", score.staff),
        ("second", "staff", score.staff),
        ("first", "context", context),
        ("second", "context", context),
    ]


def test_a_change_a_rule_names_becomes_the_event_it_means() -> None:
    score: Score = build_score(measure_count=1)
    leaf: LeafRhythmicContainer = note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.QUARTER,
        step=1,
    )
    group: GroupRhythmicContainer = eighth_triplet(
        score=score, parent=score.voice, at=Fraction(1, 4)
    )
    told: list[tuple[str, str, object]] = []
    layer: IndexLayer = _layer(told=told)

    layer.on_set(score.measures[0], "_time_signature")
    layer.on_set(leaf.anchor, "_position")
    layer.on_set(leaf, "written_size")
    layer.on_set(group, "_parent")
    layer.on_list(score.document, "_measures", score.measures[0])
    layer.on_list(score.voice, "_children", leaf)
    layer.on_list(score.staff, "_contexts", object())

    assert [(name, event) for name, event, _ in told if name == "first"] == [
        ("first", "measures"),
        ("first", "anchor"),
        ("first", "leaf"),
        ("first", "group"),
        ("first", "measures"),
        ("first", "scope"),
        ("first", "staff"),
    ]
    assert [name for name, _, _ in told].count("second") == 7


def test_a_change_no_rule_names_touches_no_index() -> None:
    score: Score = build_score(measure_count=1)
    leaf: LeafRhythmicContainer = note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.QUARTER,
        step=1,
    )
    told: list[tuple[str, str, object]] = []
    layer: IndexLayer = _layer(told=told)

    layer.on_set(leaf, "_carrier")
    layer.on_set(score.measures[0], "_prev_measure")
    layer.on_list(leaf.anchor, "_starting_contexts", object())
    layer.on_list(score.voice, "_something_else", leaf)

    assert told == []


def test_an_index_that_answers_for_nothing_takes_every_event_without_effect() -> None:
    score: Score = build_score(measure_count=1)
    leaf: LeafRhythmicContainer = note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.QUARTER,
        step=1,
    )
    group: GroupRhythmicContainer = eighth_triplet(
        score=score, parent=score.voice, at=Fraction(1, 4)
    )
    index: Index = Index()

    assert index.invalidate_measures() is None
    assert index.invalidate_anchor(anchor=leaf.anchor) is None
    assert index.invalidate_leaf(leaf=leaf) is None
    assert index.invalidate_group(group=group) is None
    assert index.invalidate_scope(scope=score.voice) is None
    assert index.invalidate_staff(staff=score.staff) is None
    assert index.invalidate_context(context=score.staff.contexts[0]) is None


def test_a_context_that_comes_goes_or_moves_is_told_as_a_context_event() -> None:
    score: Score = build_score(measure_count=1)
    leaf: LeafRhythmicContainer = note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.QUARTER,
        step=1,
    )
    dynamic: DynamicChange = DynamicChange.create(
        start=leaf.anchor, voices=[score.voice], dynamic=DynamicMarking.FORTE
    )
    clef: ClefChange = next(
        context for context in score.staff.contexts if isinstance(context, ClefChange)
    )
    told: list[tuple[str, str, object]] = []
    layer: IndexLayer = _layer(told=told)

    layer.on_list(leaf.anchor, "_starting_contexts", dynamic)
    layer.on_list(leaf.anchor, "_ending_contexts", dynamic)
    layer.on_set(dynamic, "_start")
    layer.on_set(dynamic, "_voices")

    assert [(name, event, subject) for name, event, subject in told if name == "first"] == [
        ("first", "context", dynamic),
        ("first", "context", dynamic),
        ("first", "context", dynamic),
        ("first", "context", dynamic),
    ]

    told.clear()
    layer.on_list(leaf.anchor, "_starting_contexts", clef)

    assert [(name, event) for name, event, _ in told if name == "first"] == [
        ("first", "context"),
        ("first", "staff"),
    ]
