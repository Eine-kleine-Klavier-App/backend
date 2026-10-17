from dataclasses import dataclass, replace
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Note, NoteCarrier, RestCarrier
from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    RhythmicSize,
    RhythmicValue,
)
from piano_app.domain.score.document.models.relations import Tie
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
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.helpers import iter_leaves
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import InsertNoteIntent
from piano_app.domain.score.document.services.mutation.compiler.steps import Placement, place
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    ResultRef,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    CreateNoteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    CreateLeafRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.temporal import (
    CreateTemporalAnchorRequest,
)

# Every bar is 4/4, so a position on the whole timeline reads directly as
# "bar index + position inside the bar".

_OLD_STEP: int = 0  # notes already in the score
_NEW_STEP: int = 9  # notes of the insert under test


@dataclass(frozen=True, slots=True, kw_only=True)
class _Score:
    document: ScoreDocument
    voice: Voice
    staff: Staff
    measures: list[Measure]


def _score(*, bars: int) -> _Score:
    measures: list[Measure] = [Measure.create() for _ in range(bars)]
    voice: Voice = Voice()
    staff: Staff = Staff()
    document: ScoreDocument = ScoreDocument.create(
        voices=[voice], staffs=[staff], measures=measures
    )

    return _Score(document=document, voice=voice, staff=staff, measures=measures)


def _value(value: RhythmicValue, dots: int = 0) -> DottedRhythmicValue:
    return DottedRhythmicValue(value=value, dots_count=dots)


def _size(value: RhythmicValue, count: int = 1) -> RhythmicSize:
    return RhythmicSize(value=_value(value), count=count)


def _anchor(*, score: _Score, at: Fraction) -> TemporalAnchor:
    """The anchor at a timeline position, reused when it already exists."""
    measure: Measure = score.measures[int(at)]
    position: MeasurePosition = MeasurePosition.of_fraction(fraction=at - int(at))

    existing: TemporalAnchor | None = next(
        (anchor for anchor in measure.anchors if anchor.position == position),
        None,
    )
    return existing or TemporalAnchor.create(measure=measure, position=position)


def _note(
    *,
    score: _Score,
    parent: RhythmicContainerParent,
    at: Fraction,
    value: RhythmicValue,
) -> LeafRhythmicContainer:
    """An existing note already in the score (not part of the insert under test)."""
    leaf: LeafRhythmicContainer = LeafRhythmicContainer.create(
        parent=parent,
        anchor=_anchor(score=score, at=at),
        size=_size(value),
    )
    Note.create(
        note_carrier=NoteCarrier.create(owner=leaf),
        staff=score.staff,
        staff_step=_OLD_STEP,
        accidental=Accidental.NATURAL,
    )

    return leaf


def _quarters(*, score: _Score, bar: int) -> None:
    for beat in range(4):
        _note(
            score=score,
            parent=score.voice,
            at=bar + Fraction(beat, 4),
            value=RhythmicValue.QUARTER,
        )


def _group(
    *,
    score: _Score,
    parent: RhythmicContainerParent,
    at: Fraction,
    written: RhythmicSize,
    occupied: RhythmicSize,
) -> GroupRhythmicContainer:
    """A group starting at its own anchor; it is attached at once, empty, and its children
    are added afterwards."""
    return GroupRhythmicContainer.create(
        parent=parent,
        anchor=_anchor(score=score, at=at),
        written_size=written,
        occupied_size=occupied,
    )


def _eighth_triplet(*, score: _Score, parent: RhythmicContainerParent, at: Fraction) -> None:
    """Three eighths in the time of a quarter, starting at ``at``."""
    group: GroupRhythmicContainer = _group(
        score=score,
        parent=parent,
        at=at,
        written=_size(RhythmicValue.EIGHTH, count=3),
        occupied=_size(RhythmicValue.QUARTER),
    )
    for index in range(3):
        _note(
            score=score,
            parent=group,
            at=at + Fraction(index, 12),
            value=RhythmicValue.EIGHTH,
        )


def _quarter_triplet(*, score: _Score, at: Fraction) -> GroupRhythmicContainer:
    """Three quarters in the time of a half, starting at ``at``."""
    group: GroupRhythmicContainer = _group(
        score=score,
        parent=score.voice,
        at=at,
        written=_size(RhythmicValue.QUARTER, count=3),
        occupied=_size(RhythmicValue.HALF),
    )
    for index in range(3):
        _note(
            score=score,
            parent=group,
            at=at + Fraction(index, 6),
            value=RhythmicValue.QUARTER,
        )

    return group


@dataclass(frozen=True, slots=True, kw_only=True)
class _Part:
    """A placement reduced to what the tests compare."""

    in_group: bool
    measure_index: int
    position: Fraction
    written: Fraction


def _parts(*, score: _Score, placements: list[Placement]) -> list[_Part]:
    return [
        _Part(
            in_group=isinstance(placement.scope, GroupRhythmicContainer),
            measure_index=score.measures.index(placement.measure),
            position=placement.position.value,
            written=placement.written_value.fraction,
        )
        for placement in placements
    ]


def _place(*, score: _Score, at: Fraction, length: Fraction) -> list[_Part]:
    placements: list[Placement] = place(
        voice=score.voice,
        measure=score.measures[int(at)],
        position=MeasurePosition.of_fraction(fraction=at - int(at)),
        length=length,
    )

    return _parts(score=score, placements=placements)


@dataclass(frozen=True, slots=True, kw_only=True)
class _Slot:
    """A leaf of the voice reduced to what the tests compare.

    ``content`` is ``rest``, ``old`` (notes already there), ``new`` (notes of the
    insert) or ``chord`` (a new note joined an old one on the same carrier).
    """

    measure_index: int
    position: Fraction
    written: Fraction
    in_group: bool
    content: str


def _content(*, leaf: LeafRhythmicContainer) -> str:
    carrier = leaf.carrier
    if isinstance(carrier, RestCarrier):
        return "rest"

    assert isinstance(carrier, NoteCarrier)
    steps: set[int] = {note.staff_step for note in carrier.notes}
    if steps == {_NEW_STEP}:
        return "new"
    if steps == {_OLD_STEP}:
        return "old"

    return "chord"


def _layout(*, score: _Score) -> list[_Slot]:
    return [
        _Slot(
            measure_index=score.measures.index(leaf.anchor.measure),
            position=leaf.anchor.position.value,
            written=leaf.written_size.fraction,
            in_group=isinstance(leaf.parent, GroupRhythmicContainer),
            content=_content(leaf=leaf),
        )
        for leaf in iter_leaves(score.voice)
    ]


def _ties(*, score: _Score) -> list[tuple[int, int]]:
    """Every tie as (index of the leaf it starts on, index of the leaf it ends on)."""
    leaves: list[LeafRhythmicContainer] = iter_leaves(score.voice)
    ties: set[tuple[int, int]] = set()

    for index, leaf in enumerate(leaves):
        if not isinstance(leaf.carrier, NoteCarrier):
            continue
        for note in leaf.carrier.notes:
            for relation in note.relations:
                if isinstance(relation, Tie) and relation.start is note:
                    end_leaf = relation.end.note_carrier.owner
                    assert isinstance(end_leaf, LeafRhythmicContainer)
                    ties.add((index, leaves.index(end_leaf)))

    return sorted(ties)


def _tied_notes_are_new(*, score: _Score) -> bool:
    """A tie of the insert must join the inserted notes, never an old note."""
    return all(
        relation.start.staff_step == _NEW_STEP and relation.end.staff_step == _NEW_STEP
        for leaf in iter_leaves(score.voice)
        if isinstance(leaf.carrier, NoteCarrier)
        for note in leaf.carrier.notes
        for relation in note.relations
        if isinstance(relation, Tie)
    )


def _insert(
    *,
    score: _Score,
    at: Fraction,
    value: RhythmicValue,
    dots: int = 0,
) -> MutationLog:
    intent: InsertNoteIntent = InsertNoteIntent(
        voice_id=score.voice.id,
        staff_id=score.staff.id,
        measure_id=score.measures[int(at)].id,
        position=MeasurePosition.of_fraction(fraction=at - int(at)),
        written_value=_value(value, dots),
        staff_step=_NEW_STEP,
        accidental=Accidental.NATURAL,
    )

    return build_engine().process(
        document=score.document,
        requests=build_compiler().compile(document=score.document, intent=intent),
    )


def _slot(
    bar: int,
    position: Fraction,
    written: Fraction,
    content: str,
    *,
    in_group: bool = False,
) -> _Slot:
    return _Slot(
        measure_index=bar,
        position=position,
        written=written,
        in_group=in_group,
        content=content,
    )


_Q: Fraction = Fraction(1, 4)


# --- place: the parts of an item ---------------------------------------------------


@pytest.mark.unit
def test_an_item_inside_one_measure_is_one_part_equal_to_itself() -> None:
    """No barline, no special path: the same mechanism simply yields a single part."""
    score: _Score = _score(bars=2)

    assert _place(score=score, at=Fraction(0), length=_Q) == [
        _Part(in_group=False, measure_index=0, position=Fraction(0), written=_Q),
    ]


@pytest.mark.unit
def test_an_item_is_cut_at_the_barline_it_crosses() -> None:
    score: _Score = _score(bars=2)

    assert _place(score=score, at=Fraction(3, 4), length=Fraction(1, 2)) == [
        _Part(in_group=False, measure_index=0, position=Fraction(3, 4), written=_Q),
        _Part(in_group=False, measure_index=1, position=Fraction(0), written=_Q),
    ]


@pytest.mark.unit
def test_an_item_is_cut_at_every_barline_it_crosses() -> None:
    score: _Score = _score(bars=3)

    assert _place(score=score, at=Fraction(3, 4), length=Fraction(3, 2)) == [
        _Part(in_group=False, measure_index=0, position=Fraction(3, 4), written=_Q),
        _Part(in_group=False, measure_index=1, position=Fraction(0), written=Fraction(1)),
        _Part(in_group=False, measure_index=2, position=Fraction(0), written=_Q),
    ]


@pytest.mark.unit
def test_a_cut_no_single_value_can_spell_becomes_consecutive_values() -> None:
    """5/8 left in the second bar is no single value: it is written as a half and an
    eighth, each its own part at its own position."""
    score: _Score = _score(bars=2)

    assert _place(score=score, at=Fraction(5, 8), length=Fraction(1)) == [
        _Part(in_group=False, measure_index=0, position=Fraction(5, 8), written=Fraction(3, 8)),
        _Part(in_group=False, measure_index=1, position=Fraction(0), written=Fraction(1, 2)),
        _Part(in_group=False, measure_index=1, position=Fraction(1, 2), written=Fraction(1, 8)),
    ]


@pytest.mark.unit
def test_an_item_ten_measures_long_goes_the_same_way() -> None:
    """No limit on length: a quarter, nine whole bars and a dotted half."""
    score: _Score = _score(bars=12)

    parts: list[_Part] = _place(score=score, at=Fraction(3, 4), length=Fraction(10))

    assert [part.written for part in parts] == [_Q, *[Fraction(1)] * 9, Fraction(3, 4)]
    assert [part.measure_index for part in parts] == list(range(11))
    assert [part.position for part in parts] == [Fraction(3, 4), *[Fraction(0)] * 10]


@pytest.mark.unit
def test_a_start_on_a_groups_first_instant_is_inside_the_group() -> None:
    """Half-open like every region: the group owns its own start."""
    score: _Score = _score(bars=2)
    _eighth_triplet(score=score, parent=score.voice, at=Fraction(1))

    assert _place(score=score, at=Fraction(1), length=Fraction(1, 8)) == [
        _Part(in_group=True, measure_index=1, position=Fraction(0), written=Fraction(1, 8)),
    ]


@pytest.mark.unit
def test_an_item_inside_a_group_is_cut_at_a_barline_in_the_groups_own_units() -> None:
    """A group crossing a barline is no special case: the barline is projected into the
    group, and the parts are written in its units — a written half in a quarter-note
    triplet sounds 1/3, cut into 1/4 + 1/12 sounding, written as a dotted quarter and an
    eighth. Both parts stay in the group."""
    score: _Score = _score(bars=2)
    _quarter_triplet(score=score, at=Fraction(3, 4))

    assert _place(score=score, at=Fraction(3, 4), length=Fraction(1, 2)) == [
        _Part(in_group=True, measure_index=0, position=Fraction(3, 4), written=Fraction(3, 8)),
        _Part(in_group=True, measure_index=1, position=Fraction(0), written=Fraction(1, 8)),
    ]


@pytest.mark.unit
def test_a_part_beginning_where_a_group_begins_keeps_the_items_scope() -> None:
    """The scope is chosen once, from the item's start. A voice-level note whose second
    part begins exactly where a triplet begins must not fall into that triplet."""
    score: _Score = _score(bars=2)
    _eighth_triplet(score=score, parent=score.voice, at=Fraction(1))

    assert _place(score=score, at=Fraction(3, 4), length=Fraction(1, 2)) == [
        _Part(in_group=False, measure_index=0, position=Fraction(3, 4), written=_Q),
        _Part(in_group=False, measure_index=1, position=Fraction(0), written=_Q),
    ]


@pytest.mark.unit
def test_a_note_tearing_out_of_its_group_is_refused_even_on_a_barline() -> None:
    """The group ends together with the measure: cutting at that barline would split the
    note exactly at the group's end and hide the straddle. The fit is checked first."""
    score: _Score = _score(bars=2)
    _eighth_triplet(score=score, parent=score.voice, at=Fraction(3, 4))

    with pytest.raises(MutationRejectedError, match="does not fit in its scope"):
        _place(score=score, at=Fraction(3, 4) + Fraction(1, 12), length=Fraction(1, 2))


@pytest.mark.unit
def test_a_note_running_past_the_last_measure_is_refused() -> None:
    """The same rule as a group: the timeline ends where the last measure does."""
    score: _Score = _score(bars=2)

    with pytest.raises(MutationRejectedError, match="does not fit in its scope"):
        _place(score=score, at=Fraction(7, 4), length=Fraction(1, 2))


@pytest.mark.unit
@pytest.mark.parametrize("bar", [0, 1])
def test_a_start_past_its_own_measure_is_refused(bar: int) -> None:
    """5/4 in a 4/4 bar is a wrong address, not a point further along — in the last bar
    it would even lie off the timeline."""
    score: _Score = _score(bars=2)

    with pytest.raises(MutationRejectedError, match="at or past the end of the measure"):
        place(
            voice=score.voice,
            measure=score.measures[bar],
            position=MeasurePosition.of(numerator=5, denominator=4),
            length=_Q,
        )


@pytest.mark.unit
def test_a_cut_no_value_can_spell_is_refused() -> None:
    """A thirty-second starting 1/64 before the barline leaves a 1/64 cut."""
    score: _Score = _score(bars=2)

    with pytest.raises(MutationRejectedError, match="Cannot spell"):
        _place(score=score, at=Fraction(63, 64), length=Fraction(1, 32))


# --- insert note: parts become tied notes ------------------------------------------


@pytest.mark.unit
def test_a_note_across_a_barline_becomes_two_tied_notes() -> None:
    score: _Score = _score(bars=2)

    _insert(score=score, at=Fraction(3, 4), value=RhythmicValue.HALF)

    assert _layout(score=score) == [
        _slot(0, Fraction(0), Fraction(3, 4), "rest"),
        _slot(0, Fraction(3, 4), _Q, "new"),
        _slot(1, Fraction(0), _Q, "new"),
        _slot(1, Fraction(1, 4), Fraction(3, 4), "rest"),
    ]
    assert _ties(score=score) == [(1, 2)]


@pytest.mark.unit
def test_a_note_across_two_barlines_is_one_chain_of_ties() -> None:
    score: _Score = _score(bars=3)

    _insert(score=score, at=Fraction(3, 4), value=RhythmicValue.WHOLE, dots=1)

    assert _layout(score=score) == [
        _slot(0, Fraction(0), Fraction(3, 4), "rest"),
        _slot(0, Fraction(3, 4), _Q, "new"),
        _slot(1, Fraction(0), Fraction(1), "new"),
        _slot(2, Fraction(0), _Q, "new"),
        _slot(2, Fraction(1, 4), Fraction(3, 4), "rest"),
    ]
    assert _ties(score=score) == [(1, 2), (2, 3)]


@pytest.mark.unit
def test_every_value_of_a_cut_is_tied_to_the_next() -> None:
    """A cut written as several values is tied inside itself too, not only at the
    barline: q. | h ~ e is one chain of three notes."""
    score: _Score = _score(bars=2)

    _insert(score=score, at=Fraction(5, 8), value=RhythmicValue.WHOLE)

    assert _layout(score=score) == [
        _slot(0, Fraction(0), Fraction(1, 2), "rest"),
        _slot(0, Fraction(1, 2), Fraction(1, 8), "rest"),
        _slot(0, Fraction(5, 8), Fraction(3, 8), "new"),
        _slot(1, Fraction(0), Fraction(1, 2), "new"),
        _slot(1, Fraction(1, 2), Fraction(1, 8), "new"),
        _slot(1, Fraction(5, 8), Fraction(3, 8), "rest"),
    ]
    assert _ties(score=score) == [(2, 3), (3, 4)]


@pytest.mark.unit
def test_parts_joining_existing_chords_tie_the_new_notes_only() -> None:
    """Each part lands on a same-size note and joins it as a chord; the tie must connect
    the inserted notes, leaving the old ones untied."""
    score: _Score = _score(bars=2)
    _quarters(score=score, bar=0)
    _quarters(score=score, bar=1)

    _insert(score=score, at=Fraction(3, 4), value=RhythmicValue.HALF)

    assert [slot.content for slot in _layout(score=score)] == [
        "old", "old", "old", "chord", "chord", "old", "old", "old",
    ]  # fmt: skip
    assert _ties(score=score) == [(3, 4)]
    assert _tied_notes_are_new(score=score)


@pytest.mark.unit
def test_a_group_at_the_next_barline_is_displaced_not_entered() -> None:
    """The second part stays in the voice, so the triplet it runs into is displaced as a
    whole — exactly what the same note would do without a barline."""
    score: _Score = _score(bars=2)
    _quarters(score=score, bar=0)
    _eighth_triplet(score=score, parent=score.voice, at=Fraction(1))
    for beat in range(1, 4):
        _note(
            score=score,
            parent=score.voice,
            at=1 + Fraction(beat, 4),
            value=RhythmicValue.QUARTER,
        )

    _insert(score=score, at=Fraction(3, 4), value=RhythmicValue.HALF)

    assert _layout(score=score)[3:5] == [
        _slot(0, Fraction(3, 4), _Q, "chord"),
        _slot(1, Fraction(0), _Q, "new"),
    ]
    assert not any(slot.in_group for slot in _layout(score=score))
    assert _ties(score=score) == [(3, 4)]


@pytest.mark.unit
def test_nested_groups_at_the_next_barline_are_displaced_together() -> None:
    score: _Score = _score(bars=2)
    _quarters(score=score, bar=0)
    outer: GroupRhythmicContainer = _group(
        score=score,
        parent=score.voice,
        at=Fraction(1),
        written=_size(RhythmicValue.EIGHTH, count=3),
        occupied=_size(RhythmicValue.QUARTER),
    )
    # sixteenth triplet in the room of the outer triplet's first eighth: each sixteenth
    # sounds 1/16 * 2/3 * 2/3 = 1/36
    inner: GroupRhythmicContainer = _group(
        score=score,
        parent=outer,
        at=Fraction(1),
        written=_size(RhythmicValue.SIXTEENTH, count=3),
        occupied=_size(RhythmicValue.EIGHTH),
    )
    for index in range(3):
        _note(
            score=score,
            parent=inner,
            at=1 + Fraction(index, 36),
            value=RhythmicValue.SIXTEENTH,
        )
    for index in (1, 2):
        _note(
            score=score,
            parent=outer,
            at=1 + Fraction(index, 12),
            value=RhythmicValue.EIGHTH,
        )
    for beat in range(1, 4):
        _note(
            score=score,
            parent=score.voice,
            at=1 + Fraction(beat, 4),
            value=RhythmicValue.QUARTER,
        )

    _insert(score=score, at=Fraction(3, 4), value=RhythmicValue.HALF)

    assert not any(slot.in_group for slot in _layout(score=score))
    assert _layout(score=score)[4] == _slot(1, Fraction(0), _Q, "new")
    assert _ties(score=score) == [(3, 4)]


@pytest.mark.unit
def test_a_group_straddling_the_barline_before_the_note_is_displaced_by_the_first_part() -> None:
    """The first part already displaces the triplet; the second then lands in the voice,
    with no group left for it to fall into."""
    score: _Score = _score(bars=2)
    for beat in range(3):
        _note(score=score, parent=score.voice, at=Fraction(beat, 4), value=RhythmicValue.QUARTER)
    _note(score=score, parent=score.voice, at=Fraction(3, 4), value=RhythmicValue.EIGHTH)
    _eighth_triplet(score=score, parent=score.voice, at=Fraction(7, 8))
    _note(score=score, parent=score.voice, at=Fraction(9, 8), value=RhythmicValue.EIGHTH)
    for beat in range(1, 4):
        _note(
            score=score,
            parent=score.voice,
            at=1 + Fraction(beat, 4),
            value=RhythmicValue.QUARTER,
        )

    _insert(score=score, at=Fraction(3, 4), value=RhythmicValue.HALF)

    assert _layout(score=score) == [
        _slot(0, Fraction(0), _Q, "old"),
        _slot(0, Fraction(1, 4), _Q, "old"),
        _slot(0, Fraction(1, 2), _Q, "old"),
        _slot(0, Fraction(3, 4), _Q, "new"),
        _slot(1, Fraction(0), _Q, "new"),
        _slot(1, Fraction(1, 4), _Q, "old"),
        _slot(1, Fraction(1, 2), _Q, "old"),
        _slot(1, Fraction(3, 4), _Q, "old"),
    ]
    assert _ties(score=score) == [(3, 4)]


@pytest.mark.unit
def test_a_note_inside_a_group_is_cut_at_the_barline_and_tied_inside_the_group() -> None:
    score: _Score = _score(bars=2)
    for beat in range(3):
        _note(score=score, parent=score.voice, at=Fraction(beat, 4), value=RhythmicValue.QUARTER)
    _quarter_triplet(score=score, at=Fraction(3, 4))
    for beat in range(1, 4):
        _note(
            score=score,
            parent=score.voice,
            at=1 + Fraction(beat, 4),
            value=RhythmicValue.QUARTER,
        )

    _insert(score=score, at=Fraction(3, 4), value=RhythmicValue.HALF)

    assert _layout(score=score)[3:6] == [
        _slot(0, Fraction(3, 4), Fraction(3, 8), "new", in_group=True),
        _slot(1, Fraction(0), Fraction(1, 8), "new", in_group=True),
        _slot(1, Fraction(1, 12), _Q, "old", in_group=True),
    ]
    assert _ties(score=score) == [(3, 4)]


@pytest.mark.unit
def test_a_sliced_note_is_one_gesture_and_rolls_back_as_one() -> None:
    """All the parts, their ties and the rests they wake are one journal."""
    score: _Score = _score(bars=3)

    log: MutationLog = _insert(score=score, at=Fraction(3, 4), value=RhythmicValue.WHOLE, dots=1)
    log.rollback()

    assert score.voice.children == []
    assert all(measure.anchors == [] for measure in score.measures)


@pytest.mark.unit
def test_a_refused_insert_leaves_the_score_untouched() -> None:
    """Refusals come from the compiler, before any request runs."""
    score: _Score = _score(bars=2)
    _quarters(score=score, bar=0)
    before: list[_Slot] = _layout(score=score)

    with pytest.raises(MutationRejectedError):
        _insert(score=score, at=Fraction(7, 4), value=RhythmicValue.HALF)

    assert _layout(score=score) == before


# --- refusals ------------------------------------------------------------------------
# Every case here is a correct refusal: the right outcome is the error, and the score
# must come out of it exactly as it went in.


@pytest.mark.unit
def test_a_note_tearing_out_of_a_group_in_the_middle_of_a_measure_is_refused() -> None:
    """No barline involved at all: the fit rule alone refuses it. A quarter from the
    triplet's third eighth needs written 1/4 where only 1/8 is left."""
    score: _Score = _score(bars=1)
    _eighth_triplet(score=score, parent=score.voice, at=Fraction(1, 4))

    with pytest.raises(MutationRejectedError, match="does not fit in its scope"):
        _place(score=score, at=Fraction(1, 4) + Fraction(2, 12), length=_Q)


@pytest.mark.unit
def test_a_note_tearing_out_of_a_nested_group_is_refused_though_it_fits_the_outer() -> None:
    """The scope is the innermost group: fitting the outer triplet does not help a note
    that outgrows the sixteenth triplet it starts in."""
    score: _Score = _score(bars=2)
    outer: GroupRhythmicContainer = _group(
        score=score,
        parent=score.voice,
        at=Fraction(1),
        written=_size(RhythmicValue.EIGHTH, count=3),
        occupied=_size(RhythmicValue.QUARTER),
    )
    inner: GroupRhythmicContainer = _group(
        score=score,
        parent=outer,
        at=Fraction(1),
        written=_size(RhythmicValue.SIXTEENTH, count=3),
        occupied=_size(RhythmicValue.EIGHTH),
    )
    for index in range(3):
        _note(score=score, parent=inner, at=1 + Fraction(index, 36), value=RhythmicValue.SIXTEENTH)
    for index in (1, 2):
        _note(score=score, parent=outer, at=1 + Fraction(index, 12), value=RhythmicValue.EIGHTH)

    # a quarter fits the outer triplet's written 3/8, but not the inner's written 3/16
    with pytest.raises(MutationRejectedError, match="does not fit in its scope"):
        _place(score=score, at=Fraction(1), length=_Q)


@pytest.mark.unit
def test_a_note_inside_a_group_crossing_a_barline_is_refused_when_it_outgrows_the_group() -> None:
    """Crossing the barline inside the group is fine; running past the group's end is not,
    wherever that end falls."""
    score: _Score = _score(bars=2)
    _quarter_triplet(score=score, at=Fraction(3, 4))

    # the triplet's written interior is 3/4; a written whole from its start outgrows it
    with pytest.raises(MutationRejectedError, match="does not fit in its scope"):
        _place(score=score, at=Fraction(3, 4), length=Fraction(1))


@pytest.mark.unit
def test_a_note_ending_exactly_on_its_groups_end_is_not_refused() -> None:
    """The contrast every refusal above relies on: the end bound is inclusive, so a note
    that fills its group to the last instant fits."""
    score: _Score = _score(bars=1)
    _eighth_triplet(score=score, parent=score.voice, at=Fraction(1, 4))

    assert _place(score=score, at=Fraction(1, 4) + Fraction(1, 12), length=_Q) == [
        _Part(
            in_group=True, measure_index=0, position=Fraction(1, 4) + Fraction(1, 12), written=_Q
        ),
    ]


@pytest.mark.unit
def test_a_note_ending_a_sliver_past_the_last_measure_is_refused() -> None:
    score: _Score = _score(bars=1)

    with pytest.raises(MutationRejectedError, match="does not fit in its scope"):
        _place(score=score, at=Fraction(3, 4), length=_Q + Fraction(1, 32))


@pytest.mark.unit
def test_a_long_note_running_off_a_short_score_is_refused_whole() -> None:
    """Ten bars asked of a five-bar score: nothing is placed, not even the bars that
    exist — the tail is never silently dropped."""
    score: _Score = _score(bars=5)

    with pytest.raises(MutationRejectedError, match="does not fit in its scope"):
        _place(score=score, at=Fraction(0), length=Fraction(10))


@pytest.mark.unit
def test_a_position_exactly_at_the_measure_end_is_refused() -> None:
    """The end of a bar is the start of the next one, never a slot of its own."""
    score: _Score = _score(bars=2)

    with pytest.raises(MutationRejectedError, match="at or past the end of the measure"):
        place(
            voice=score.voice,
            measure=score.measures[0],
            position=MeasurePosition.of(numerator=1, denominator=1),
            length=_Q,
        )


@pytest.mark.unit
def test_a_position_is_checked_against_its_own_measures_length() -> None:
    """3/4 is inside a 4/4 bar but past the end of a 3/4 bar."""
    three_four: Measure = Measure.create(time_signature=_size(RhythmicValue.QUARTER, count=3))
    voice: Voice = Voice()
    ScoreDocument.create(voices=[voice], staffs=[Staff()], measures=[three_four, Measure.create()])

    with pytest.raises(MutationRejectedError, match="at or past the end of the measure"):
        place(
            voice=voice,
            measure=three_four,
            position=MeasurePosition.of(numerator=3, denominator=4),
            length=_Q,
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "wrong"),
    [
        ("voice_id", "staff"),
        ("staff_id", "voice"),
        ("measure_id", "voice"),
    ],
)
def test_an_id_naming_the_wrong_kind_of_entity_is_refused(field: str, wrong: str) -> None:
    score: _Score = _score(bars=1)
    ids: dict[str, str] = {"staff": score.staff.id, "voice": score.voice.id}
    intent: InsertNoteIntent = replace(
        InsertNoteIntent(
            voice_id=score.voice.id,
            staff_id=score.staff.id,
            measure_id=score.measures[0].id,
            position=MeasurePosition.of(numerator=0, denominator=1),
            written_value=_value(RhythmicValue.QUARTER),
            staff_step=_NEW_STEP,
            accidental=Accidental.NATURAL,
        ),
        **{field: ids[wrong]},
    )

    with pytest.raises(MutationRejectedError, match="must be"):
        build_compiler().compile(document=score.document, intent=intent)


@pytest.mark.unit
def test_an_unknown_id_is_refused() -> None:
    score: _Score = _score(bars=1)
    intent: InsertNoteIntent = InsertNoteIntent(
        voice_id="nowhere",
        staff_id=score.staff.id,
        measure_id=score.measures[0].id,
        position=MeasurePosition.of(numerator=0, denominator=1),
        written_value=_value(RhythmicValue.QUARTER),
        staff_step=_NEW_STEP,
        accidental=Accidental.NATURAL,
    )

    with pytest.raises(MutationRejectedError, match="nowhere"):
        build_compiler().compile(document=score.document, intent=intent)


@pytest.mark.unit
def test_the_leaf_analyzer_refuses_a_voice_level_leaf_past_the_score_end() -> None:
    """The invariant's owner holds it for any source of requests, not only for what the
    compiler already checked: a request sent straight to the engine is refused too."""
    score: _Score = _score(bars=1)

    with pytest.raises(MutationRejectedError, match="Container does not fit in its scope"):
        build_engine().process(
            document=score.document,
            requests=[
                CreateLeafRequest(
                    scope=score.voice,
                    measure=score.measures[0],
                    position=MeasurePosition.of(numerator=3, denominator=4),
                    size=_size(RhythmicValue.HALF),
                    out=ResultRef[LeafRhythmicContainer](),
                )
            ],
        )


@pytest.mark.unit
def test_the_leaf_analyzer_refuses_a_leaf_outgrowing_the_group_it_is_given() -> None:
    score: _Score = _score(bars=1)
    _eighth_triplet(score=score, parent=score.voice, at=Fraction(0))
    group = score.voice.children[0]
    assert isinstance(group, GroupRhythmicContainer)

    with pytest.raises(MutationRejectedError, match="Container does not fit in its scope"):
        build_engine().process(
            document=score.document,
            requests=[
                CreateLeafRequest(
                    scope=group,
                    measure=score.measures[0],
                    # the third eighth: written 1/4 in, a quarter needs up to 1/2 of 3/8
                    position=MeasurePosition.of(numerator=2, denominator=12),
                    size=_size(RhythmicValue.QUARTER),
                    out=ResultRef[LeafRhythmicContainer](),
                )
            ],
        )


@pytest.mark.unit
def test_the_anchor_analyzer_refuses_a_position_past_its_measure() -> None:
    score: _Score = _score(bars=2)

    with pytest.raises(MutationRejectedError, match="at or past the end of the measure"):
        build_engine().process(
            document=score.document,
            requests=[
                CreateTemporalAnchorRequest(
                    measure=score.measures[0],
                    position=MeasurePosition.of(numerator=5, denominator=4),
                    out=ResultRef[TemporalAnchor](),
                )
            ],
        )


@pytest.mark.unit
def test_a_gesture_refused_halfway_is_rolled_back_entirely() -> None:
    """The first request of the gesture runs and changes the score; the second is
    refused — nothing of the first may survive."""
    score: _Score = _score(bars=1)
    _quarters(score=score, bar=0)
    before: list[_Slot] = _layout(score=score)

    with pytest.raises(MutationRejectedError, match="Container does not fit in its scope"):
        build_engine().process(
            document=score.document,
            requests=[
                CreateNoteRequest(
                    scope=score.voice,
                    staff=score.staff,
                    measure=score.measures[0],
                    position=MeasurePosition.of(numerator=0, denominator=1),
                    written_value=_value(RhythmicValue.HALF),
                    staff_step=_NEW_STEP,
                    accidental=Accidental.NATURAL,
                    out=ResultRef[Note](),
                ),
                CreateLeafRequest(
                    scope=score.voice,
                    measure=score.measures[0],
                    position=MeasurePosition.of(numerator=3, denominator=4),
                    size=_size(RhythmicValue.HALF),
                    out=ResultRef[LeafRhythmicContainer](),
                ),
            ],
        )

    assert _layout(score=score) == before


@pytest.mark.unit
@pytest.mark.parametrize(
    ("at", "value", "dots"),
    [
        (Fraction(7, 4), RhythmicValue.HALF, 0),  # past the last bar
        (Fraction(3, 4) + Fraction(1, 12), RhythmicValue.HALF, 0),  # tears out of the triplet
    ],
)
def test_every_refused_insert_leaves_the_score_exactly_as_it_was(
    at: Fraction,
    value: RhythmicValue,
    dots: int,
) -> None:
    score: _Score = _score(bars=2)
    for beat in range(3):
        _note(score=score, parent=score.voice, at=Fraction(beat, 4), value=RhythmicValue.QUARTER)
    _eighth_triplet(score=score, parent=score.voice, at=Fraction(3, 4))
    _quarters(score=score, bar=1)
    before: list[_Slot] = _layout(score=score)

    with pytest.raises(MutationRejectedError):
        _insert(score=score, at=at, value=value, dots=dots)

    assert _layout(score=score) == before
