from fractions import Fraction

import pytest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import ClefChange, Slur
from piano_app.domain.score.document.models.material import Carrier, Note
from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.score.document.models.notation import (
    Clef,
    GlissandoType,
    RhythmicSize,
    RhythmicValue,
)
from piano_app.domain.score.document.models.relations import Beam, Glissando, Tie
from piano_app.domain.score.document.models.structural import (
    MEASURE_START,
    Measure,
    MeasurePosition,
    TemporalAnchor,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog

from ..scene import (
    Score,
    anchor_at,
    build_score,
    find_carriers,
    group,
    note,
    note_at,
    quarters,
    size,
)

# The model operations the measure operations and the tuplet split rely on. Each one keeps
# its own entity's links and indexes consistent; whether the result fits the music around it
# is its caller's decision.


# --- ScoreDocument.insert_measure_before ------------------------------------------------


def _beyond_the_start(measure: Measure) -> list[TemporalAnchor]:
    """The anchors of a measure other than the one at its start, which the first measure
    always holds for the contexts every score starts with."""
    return [anchor for anchor in measure.anchors if anchor.position != MEASURE_START]


@pytest.mark.unit
def test_a_measure_inserted_before_a_middle_one_is_linked_between_its_neighbours() -> None:
    score: Score = build_score(measure_count=2)
    first, second = score.measures
    inserted: Measure = Measure.create()

    score.document.insert_measure_before(measure=inserted, before=second)

    assert list(score.document.measures) == [first, inserted, second]
    assert (first.next_measure, inserted.prev_measure) == (inserted, first)
    assert (inserted.next_measure, second.prev_measure) == (second, inserted)


@pytest.mark.unit
def test_a_measure_inserted_before_the_first_one_heads_the_chain() -> None:
    score: Score = build_score(measure_count=1)
    inserted: Measure = Measure.create()

    score.document.insert_measure_before(measure=inserted, before=score.measures[0])

    assert list(score.document.measures) == [inserted, score.measures[0]]
    assert inserted.prev_measure is None
    assert inserted.next_measure is score.measures[0]
    assert score.measures[0].prev_measure is inserted


@pytest.mark.unit
def test_inserting_before_a_measure_of_another_document_is_refused() -> None:
    score: Score = build_score(measure_count=1)
    stranger: Measure = Measure.create()

    with pytest.raises(ValueError, match="not in the document"):
        score.document.insert_measure_before(measure=Measure.create(), before=stranger)


@pytest.mark.unit
def test_inserting_a_measure_already_in_another_chain_is_refused() -> None:
    score: Score = build_score(measure_count=1)
    chained: Measure = Measure.create()
    ScoreDocument.create(voices=[], staffs=[], measures=[chained, Measure.create()])

    with pytest.raises(ValueError, match="already in a chain"):
        score.document.insert_measure_before(measure=chained, before=score.measures[0])


@pytest.mark.unit
def test_inserting_a_measure_already_in_the_document_changes_nothing() -> None:
    score: Score = build_score(measure_count=2)

    score.document.insert_measure_before(measure=score.measures[1], before=score.measures[0])

    assert list(score.document.measures) == score.measures


# --- GroupRhythmicContainer.split_at -----------------------------------------------------


def _sextuplet_across_the_barline() -> tuple[Score, GroupRhythmicContainer]:
    """Six eighths (staff steps 1-6) in the time of a half from beat four over the barline."""
    score: Score = build_score(measure_count=2)
    sextuplet: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(3, 4),
        written=size(RhythmicValue.EIGHTH, count=6),
        occupied=size(RhythmicValue.HALF),
    )
    for index in range(6):
        note(
            score=score,
            parent=sextuplet,
            at=Fraction(3, 4) + index * Fraction(1, 12),
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index + 1,
        )

    return score, sextuplet


type _SplitState = tuple[
    list[RhythmicContainer],
    list[list[RhythmicContainer]],
    list[RhythmicContainerParent],
    list[tuple[RhythmicSize, RhythmicSize]],
    list[list[RhythmicContainer]],
]


def _split_state(*, score: Score) -> _SplitState:
    """Everything a split touches, by identity: the voice's children, each group's children,
    each leaf's parent, each group's sizes and each anchor's containers."""
    groups: list[GroupRhythmicContainer] = [
        child for child in score.voice.children if isinstance(child, GroupRhythmicContainer)
    ]
    leaves: list[RhythmicContainer] = [leaf for item in groups for leaf in item.children]
    return (
        list(score.voice.children),
        [list(item.children) for item in groups],
        [leaf.parent for leaf in leaves],
        [(item.written_size, item.occupied_size) for item in groups],
        [list(anchor.containers) for measure in score.measures for anchor in measure.anchors],
    )


def _split_at_the_barline(
    *,
    score: Score,
    sextuplet: GroupRhythmicContainer,
    sink: MutationSink = DIRECT_SINK,
) -> GroupRhythmicContainer:
    return sextuplet.split_at(
        anchor=anchor_at(score=score, at=Fraction(1)),
        first_written_size=_E3,
        first_occupied_size=_Q1,
        second_written_size=_E3,
        second_occupied_size=_Q1,
        sink=sink,
    )


@pytest.mark.unit
def test_a_split_group_keeps_the_first_part_and_hands_the_rest_to_a_new_group() -> None:
    score, sextuplet = _sextuplet_across_the_barline()
    leaves: list[RhythmicContainer] = list(sextuplet.children)
    barline: TemporalAnchor = anchor_at(score=score, at=Fraction(1))

    second: GroupRhythmicContainer = _split_at_the_barline(score=score, sextuplet=sextuplet)

    assert (sextuplet.written_size, sextuplet.occupied_size) == (
        size(RhythmicValue.EIGHTH, count=3),
        size(RhythmicValue.QUARTER),
    )
    assert (second.written_size, second.occupied_size) == (
        size(RhythmicValue.EIGHTH, count=3),
        size(RhythmicValue.QUARTER),
    )
    assert second.parent is score.voice
    assert second.start_anchor is barline
    assert list(score.voice.children) == [sextuplet, second]
    assert list(sextuplet.children) == leaves[:3]
    assert list(second.children) == leaves[3:]
    assert all(leaf.parent is second for leaf in leaves[3:])
    # listed before the leaf it holds there, as restoring the document would list them
    assert list(barline.containers) == [second, leaves[3]]


_E3: RhythmicSize = size(RhythmicValue.EIGHTH, count=3)
_Q1: RhythmicSize = size(RhythmicValue.QUARTER)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("parts", "reason"),
    [
        ((_E3, _Q1, size(RhythmicValue.EIGHTH, count=2), _Q1), "exactly its sizes"),
        (
            (size(RhythmicValue.EIGHTH, count=2), _Q1, size(RhythmicValue.EIGHTH, count=4), _Q1),
            "keep its ratio",
        ),
        (
            (
                size(RhythmicValue.SIXTEENTH, count=3),
                size(RhythmicValue.EIGHTH),
                size(RhythmicValue.SIXTEENTH, count=9),
                size(RhythmicValue.EIGHTH, count=3),
            ),
            "cannot hold its children",
        ),
    ],
    ids=["sizes", "ratio", "first-part-room"],
)
def test_a_split_with_inconsistent_parts_is_refused_and_changes_nothing(
    parts: tuple[RhythmicSize, RhythmicSize, RhythmicSize, RhythmicSize],
    reason: str,
) -> None:
    """The parts as (first written, first occupied, second written, second occupied); at the
    barline the first part keeps three eighths, so three sixteenths cannot hold them."""
    score, sextuplet = _sextuplet_across_the_barline()
    before: _SplitState = _split_state(score=score)

    with pytest.raises(ValueError, match=reason):
        sextuplet.split_at(
            anchor=anchor_at(score=score, at=Fraction(1)),
            first_written_size=parts[0],
            first_occupied_size=parts[1],
            second_written_size=parts[2],
            second_occupied_size=parts[3],
        )

    assert _split_state(score=score) == before


@pytest.mark.unit
def test_undo_and_redo_of_a_split_restore_each_side_exactly() -> None:
    score, sextuplet = _sextuplet_across_the_barline()
    before: _SplitState = _split_state(score=score)
    log: MutationLog = MutationLog()

    second: GroupRhythmicContainer = _split_at_the_barline(
        score=score,
        sextuplet=sextuplet,
        sink=log,
    )
    after: _SplitState = _split_state(score=score)

    log.rollback()
    assert _split_state(score=score) == before

    log.reapply()
    assert _split_state(score=score) == after
    assert list(score.voice.children) == [sextuplet, second]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("at", "reason"),
    [
        (Fraction(1, 2), "strictly inside"),  # before the group's start
        (Fraction(3, 4), "strictly inside"),  # on its start
        (Fraction(5, 4), "strictly inside"),  # on its end
    ],
    ids=["before", "on-start", "on-end"],
)
def test_a_split_at_an_anchor_outside_the_group_is_refused_and_changes_nothing(
    at: Fraction,
    reason: str,
) -> None:
    score, sextuplet = _sextuplet_across_the_barline()
    outside: TemporalAnchor = anchor_at(score=score, at=at)
    before: _SplitState = _split_state(score=score)

    with pytest.raises(ValueError, match=reason):
        sextuplet.split_at(
            anchor=outside,
            first_written_size=_E3,
            first_occupied_size=_Q1,
            second_written_size=_E3,
            second_occupied_size=_Q1,
        )

    assert _split_state(score=score) == before


@pytest.mark.unit
def test_a_split_whose_second_part_cannot_hold_its_children_is_refused_and_changes_nothing() -> (
    None
):
    """Split after the first eighth with halves of three eighths each: five eighths would
    move into a part written for three."""
    score, sextuplet = _sextuplet_across_the_barline()
    after_first: TemporalAnchor = anchor_at(score=score, at=Fraction(3, 4) + Fraction(1, 12))
    before: _SplitState = _split_state(score=score)

    with pytest.raises(ValueError, match="second part of a split group cannot hold"):
        sextuplet.split_at(
            anchor=after_first,
            first_written_size=_E3,
            first_occupied_size=_Q1,
            second_written_size=_E3,
            second_occupied_size=_Q1,
        )

    assert _split_state(score=score) == before


# --- Beam.narrow_to ----------------------------------------------------------------------


def _five_beamed_eighths() -> tuple[list[Carrier], Beam]:
    score: Score = build_score(measure_count=1)
    leaves: list[LeafRhythmicContainer] = [
        note(
            score=score,
            parent=score.voice,
            at=index * Fraction(1, 8),
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index + 1,
        )
        for index in range(5)
    ]
    carriers: list[Carrier] = find_carriers(containers=leaves)

    return carriers, Beam.create(carriers=carriers)


@pytest.mark.unit
def test_a_beam_narrowed_to_a_run_keeps_only_that_run() -> None:
    carriers, beam = _five_beamed_eighths()

    beam.narrow_to(carriers=carriers[1:3])

    assert list(beam.members) == carriers[1:3]
    assert [list(carrier.carrier_group_relations) for carrier in carriers] == [
        [],
        [beam],
        [beam],
        [],
        [],
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("picked", "reason"),
    [
        ([2], "at least two"),
        ([0, 2], "consecutive members"),
        ([1, 0], "consecutive members"),
    ],
    ids=["one", "gap", "reversed"],
)
def test_a_beam_narrowed_to_anything_but_a_run_of_two_is_refused(
    picked: list[int],
    reason: str,
) -> None:
    carriers, beam = _five_beamed_eighths()

    with pytest.raises(ValueError, match=reason):
        beam.narrow_to(carriers=[carriers[index] for index in picked])

    assert list(beam.members) == carriers
    assert all(list(carrier.carrier_group_relations) == [beam] for carrier in carriers)


@pytest.mark.unit
def test_undo_and_redo_of_a_narrowed_beam_restore_each_side() -> None:
    carriers, beam = _five_beamed_eighths()
    log: MutationLog = MutationLog()

    beam.narrow_to(carriers=carriers[2:], sink=log)

    log.rollback()
    assert list(beam.members) == carriers
    assert all(list(carrier.carrier_group_relations) == [beam] for carrier in carriers)

    log.reapply()
    assert list(beam.members) == carriers[2:]
    assert [list(carrier.carrier_group_relations) for carrier in carriers[:2]] == [[], []]


# --- Beam.can_remove_carrier --------------------------------------------------------------


@pytest.mark.unit
def test_a_beam_of_three_lets_its_middle_member_leave() -> None:
    carriers, beam = _five_beamed_eighths()
    beam.narrow_to(carriers=carriers[1:4])

    assert beam.can_remove_carrier(carrier=carriers[2])


@pytest.mark.unit
def test_a_beam_of_two_lets_neither_member_leave() -> None:
    carriers, beam = _five_beamed_eighths()
    beam.narrow_to(carriers=carriers[:2])

    assert not any(beam.can_remove_carrier(carrier=carrier) for carrier in carriers[:2])


# --- NoteToNoteRelation.set_start -----------------------------------------------------------


@pytest.mark.unit
def test_a_relation_moves_its_start_keeping_itself() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    first, second, third, _ = [note_at(score=score, at=Fraction(beat, 4)) for beat in range(4)]
    glissando: Glissando = Glissando.create(
        start_note=first,
        end_note=third,
        glissando_type=GlissandoType.STRAIGHT,
    )

    glissando.set_start(start_note=second)

    assert glissando.start is second
    assert (list(first.relations), list(second.relations)) == ([], [glissando])
    assert list(third.relations) == [glissando]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("moved_to", "reason"),
    [(1, "already starts another tie"), (2, "different entities")],
    ids=["a note starting a tie", "its own end"],
)
def test_a_tie_refuses_a_start_it_cannot_take_and_changes_nothing(
    moved_to: int,
    reason: str,
) -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    notes: list[Note] = [note_at(score=score, at=Fraction(beat, 4)) for beat in range(4)]
    tie: Tie = Tie.create(start_note=notes[0], end_note=notes[2])
    taken: Tie = Tie.create(start_note=notes[1], end_note=notes[3])

    with pytest.raises(ValueError, match=reason):
        tie.set_start(start_note=notes[moved_to])

    assert tie.start is notes[0]
    assert [list(note.relations) for note in notes] == [[tie], [taken], [tie], [taken]]


# --- Context.set_start / SpanContext.set_start / set_end ---------------------------------


@pytest.mark.unit
def test_a_point_context_moves_its_start_and_its_staff_reorders_it() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    early: ClefChange = ClefChange.create(
        start=anchor_at(score=score, at=Fraction(1, 4)),
        staff=score.staff,
        clef=Clef.BASS,
    )
    late: ClefChange = ClefChange.create(
        start=anchor_at(score=score, at=Fraction(1, 2)),
        staff=score.staff,
        clef=Clef.TREBLE,
    )
    old_start: TemporalAnchor = early.start
    new_start: TemporalAnchor = anchor_at(score=score, at=Fraction(3, 4))

    early.set_start(start=new_start)

    assert early.start is new_start
    assert list(new_start.starting_contexts) == [early]
    assert list(old_start.starting_contexts) == []
    assert [context for context in score.staff.contexts if context in (early, late)] == [
        late,
        early,
    ]


@pytest.mark.unit
def test_a_span_context_moves_its_start_and_end_keeping_itself() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    slur: Slur = Slur.create(
        start=anchor_at(score=score, at=Fraction(0)),
        end=anchor_at(score=score, at=Fraction(1, 2)),
        voice=score.voice,
    )
    old_end: TemporalAnchor = slur.end

    slur.set_start(start=anchor_at(score=score, at=Fraction(1, 4)))
    slur.set_end(end=anchor_at(score=score, at=Fraction(3, 4)))

    assert slur.start is anchor_at(score=score, at=Fraction(1, 4))
    assert slur.end is anchor_at(score=score, at=Fraction(3, 4))
    assert list(slur.end.ending_contexts) == [slur]
    assert list(old_end.ending_contexts) == []
    assert slur in score.voice.contexts


@pytest.mark.unit
@pytest.mark.parametrize("at", [Fraction(1, 2), Fraction(3, 4)])
def test_a_span_context_start_must_stay_before_its_end(at: Fraction) -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    slur: Slur = Slur.create(
        start=anchor_at(score=score, at=Fraction(0)),
        end=anchor_at(score=score, at=Fraction(1, 2)),
        voice=score.voice,
    )

    with pytest.raises(ValueError, match="Start must precede end"):
        slur.set_start(start=anchor_at(score=score, at=at))

    assert slur.start is anchor_at(score=score, at=Fraction(0))
    assert slur in slur.start.starting_contexts


@pytest.mark.unit
@pytest.mark.parametrize("at", [Fraction(0), Fraction(1, 4)])
def test_a_span_context_end_must_stay_after_its_start(at: Fraction) -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    slur: Slur = Slur.create(
        start=anchor_at(score=score, at=Fraction(1, 4)),
        end=anchor_at(score=score, at=Fraction(1, 2)),
        voice=score.voice,
    )

    with pytest.raises(ValueError, match="Start must precede end"):
        slur.set_end(end=anchor_at(score=score, at=at))

    assert slur.end is anchor_at(score=score, at=Fraction(1, 2))
    assert list(slur.end.ending_contexts) == [slur]


# --- Measure.set_time_signature / TemporalAnchor.move_to (time-signature change) ------------


@pytest.mark.unit
def test_a_measure_is_not_shortened_while_an_anchor_lies_past_its_new_end() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    measure: Measure = score.measures[0]
    three_four: RhythmicSize = size(RhythmicValue.QUARTER, count=3)

    with pytest.raises(ValueError, match="end of the measure"):
        measure.set_time_signature(time_signature=three_four)

    assert measure.time_signature == size(RhythmicValue.QUARTER, count=4)

    measure.set_time_signature(time_signature=size(RhythmicValue.QUARTER, count=5))
    assert measure.time_signature.fraction == Fraction(5, 4)


@pytest.mark.unit
def test_a_moved_anchor_keeps_what_starts_at_it_and_lands_in_order() -> None:
    score: Score = build_score(measure_count=2)
    leaf: LeafRhythmicContainer = note(
        score=score,
        parent=score.voice,
        at=Fraction(3, 4),
        rhythmic_value=RhythmicValue.QUARTER,
        step=1,
    )
    anchor: TemporalAnchor = leaf.anchor
    later: TemporalAnchor = anchor_at(score=score, at=1 + Fraction(1, 2))
    log: MutationLog = MutationLog()

    anchor.move_to(
        measure=score.measures[1],
        position=MeasurePosition.of_fraction(fraction=Fraction(1, 4)),
        sink=log,
    )

    assert leaf.anchor is anchor
    assert list(anchor.containers) == [leaf]
    assert _beyond_the_start(score.measures[0]) == []
    assert list(score.measures[1].anchors) == [anchor, later]

    log.rollback()
    assert (anchor.measure, anchor.position.value) == (score.measures[0], Fraction(3, 4))
    assert _beyond_the_start(score.measures[0]) == [anchor]
    assert list(score.measures[1].anchors) == [later]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("position", "message"),
    [
        (Fraction(1, 2), "already exists"),
        (Fraction(1), "end of the measure"),
        (Fraction(3, 4), "neighbouring anchors"),
    ],
    ids=["place-taken", "past-the-end", "past-the-next-anchor"],
)
def test_an_anchor_is_not_moved_to_a_taken_or_outside_place_nor_past_a_neighbour(
    position: Fraction,
    message: str,
) -> None:
    score: Score = build_score(measure_count=2)
    anchor: TemporalAnchor = anchor_at(score=score, at=Fraction(3, 4))
    taken: TemporalAnchor = anchor_at(score=score, at=1 + Fraction(1, 2))

    with pytest.raises(ValueError, match=message):
        anchor.move_to(
            measure=score.measures[1],
            position=MeasurePosition.of_fraction(fraction=position),
        )

    assert _beyond_the_start(score.measures[0]) == [anchor]
    assert list(score.measures[1].anchors) == [taken]
