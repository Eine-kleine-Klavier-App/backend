from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import (
    Carrier,
    CarrierOwner,
    Note,
    NoteCarrier,
    Rest,
)
from piano_app.domain.score.document.models.notation import (
    Accidental,
    GlissandoType,
    RhythmicValue,
)
from piano_app.domain.score.document.models.presentation import (
    PresentationTarget,
    ReferencePoint,
    VerticalOffset,
)
from piano_app.domain.score.document.models.relations import Beam, Glissando, Tie
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.helpers import find_beams
from piano_app.domain.score.document.services.mutation.compiler import (
    TieNotesIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)
from piano_app.domain.score.document.services.presentation import (
    PresentationEditor,
    SetVerticalOffset,
)

from ...scene import (
    GroupSlot,
    Score,
    Snapshot,
    TieSlot,
    anchor_layout,
    apply_intent,
    broken_relations,
    build_score,
    crossing_half,
    crossing_triplet,
    find_tie,
    four_quarters,
    group_layout,
    layout,
    note,
    note_at,
    orphan_anchors,
    pending,
    planned_intent,
    quarters,
    rest,
    rest_at,
    slot,
    snapshot,
    tie_layout,
    triplet_scene,
    value,
)

# ChangeDuration (change-duration): one element, never the whole tie chain. The new span
# starts where the element starts; what it newly meets goes by the overwrite rule with its
# ties; a value fitting its measure resizes the leaf in place (carrier, notes, stem override
# and ids stay); a value crossing a barline keeps the same leaf as the first piece and adds
# new leaves with the notes copied and tied (rest pieces untied); a shorter value leaves room
# for fill. The incoming tie stays, the outgoing one only while the element still touches
# the next note. An item may not leave its scope.

_Q: Fraction = Fraction(1, 4)
_H: Fraction = Fraction(1, 2)
_E: Fraction = Fraction(1, 8)
_THIRD: Fraction = Fraction(1, 12)  # one triplet eighth on the timeline
_OUT_OF_SCOPE: str = "does not fit in its scope"

_PENDING = pending(stage=4)


def change_duration(
    *,
    score: Score,
    carrier: Carrier,
    rhythmic_value: RhythmicValue,
    dots: int = 0,
) -> MutationLog:
    """Run ``ChangeDurationIntent(carrier_id, written_value)`` on a note or rest carrier.

    ``written_value`` is read in the units of the element's scope.
    """
    return apply_intent(
        score=score,
        intent=planned_intent(
            "ChangeDurationIntent",
            carrier_id=carrier.id,
            written_value=value(rhythmic_value, dots),
        ),
    )


def _leaf_of(carrier: Carrier) -> LeafRhythmicContainer:
    owner: CarrierOwner = carrier.owner
    assert isinstance(owner, LeafRhythmicContainer)

    return owner


def _set_stem(*, score: Score, carrier: NoteCarrier) -> VerticalOffset:
    override = VerticalOffset(value=0.7)
    PresentationEditor().apply(
        document=score.document,
        commands=[
            SetVerticalOffset(
                target=PresentationTarget(entity_id=carrier.id, reference=ReferencePoint.STEM_TIP),
                value=override,
            )
        ],
        sink=MutationLog(),
    )

    return override


@pytest.mark.unit
@_PENDING
def test_a_longer_value_that_fits_its_measure_resizes_the_leaf_in_place() -> None:
    """A quarter becomes a half in place; the quarter rest it newly meets goes.

    The leaf, carrier, note, ids and stem override all stay; the half rest after is
    untouched.
    """
    score: Score = build_score(measure_count=1)
    note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.QUARTER,
        step=1,
    )
    rest(score=score, parent=score.voice, at=_Q, rhythmic_value=RhythmicValue.QUARTER)
    rest(score=score, parent=score.voice, at=_H, rhythmic_value=RhythmicValue.HALF)
    target: Note = note_at(score=score, at=Fraction(0))
    carrier: NoteCarrier = target.note_carrier
    leaf: LeafRhythmicContainer = _leaf_of(carrier)
    leaf_id: str = leaf.id
    override: VerticalOffset = _set_stem(score=score, carrier=carrier)
    half_rest: Rest = rest_at(score=score, at=_H)

    change_duration(score=score, carrier=carrier, rhythmic_value=RhythmicValue.HALF)

    assert layout(score=score) == [
        slot(0, Fraction(0), _H, "1"),
        slot(0, _H, _H, "rest"),
    ]
    assert note_at(score=score, at=Fraction(0)) is target
    assert target.note_carrier is carrier
    assert _leaf_of(carrier) is leaf
    assert leaf.id == leaf_id
    assert (
        score.document.presentation.vertical[
            PresentationTarget(entity_id=carrier.id, reference=ReferencePoint.STEM_TIP)
        ]
        == override
    )
    assert rest_at(score=score, at=_H) is half_rest
    assert group_layout(score=score) == []
    assert tie_layout(score=score) == []
    assert anchor_layout(score=score) == [(0, Fraction(0)), (0, _H)]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_a_longer_value_crossing_the_barline_keeps_the_leaf_and_adds_a_tied_piece() -> None:
    """A quarter becomes a dotted half: the same leaf to the barline, a tied piece after.

    The first piece keeps its leaf, note and stem override; a new quarter with the same note
    is tied after the barline; the quarters met on beat four and on beat one of measure two
    go.
    """
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(0, 1))
    note(score=score, parent=score.voice, at=_H, rhythmic_value=RhythmicValue.QUARTER, step=1)
    quarters(score=score, measure=0, beats=(3,))
    quarters(score=score, measure=1)
    target: Note = note_at(score=score, at=_H)
    leaf: LeafRhythmicContainer = _leaf_of(target.note_carrier)
    override: VerticalOffset = _set_stem(score=score, carrier=target.note_carrier)

    change_duration(
        score=score,
        carrier=target.note_carrier,
        rhythmic_value=RhythmicValue.HALF,
        dots=1,
    )

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "0"),
        slot(0, _H, _H, "1"),
        slot(1, Fraction(0), _Q, "1"),
        *[slot(1, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert tie_layout(score=score) == [TieSlot(start=(0, _H, 1), end=(1, Fraction(0), 1))]
    assert note_at(score=score, at=_H) is target
    assert _leaf_of(target.note_carrier) is leaf
    assert (
        score.document.presentation.vertical[
            PresentationTarget(entity_id=target.note_carrier.id, reference=ReferencePoint.STEM_TIP)
        ]
        == override
    )
    assert note_at(score=score, at=Fraction(1)) is not target
    assert group_layout(score=score) == []
    assert anchor_layout(score=score) == [
        (0, Fraction(0)),
        (0, _Q),
        (0, _H),
        *[(1, Fraction(beat, 4)) for beat in range(4)],
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_a_chord_cut_at_the_barline_copies_and_ties_every_note() -> None:
    """A two-note chord on beat three becomes a dotted half; both notes are tied across."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(0, 1))
    note(score=score, parent=score.voice, at=_H, rhythmic_value=RhythmicValue.QUARTER, step=1)
    quarters(score=score, measure=0, beats=(3,))
    quarters(score=score, measure=1)
    chord: NoteCarrier = note_at(score=score, at=_H).note_carrier
    Note.create(note_carrier=chord, staff=score.staff, staff_step=2, accidental=Accidental.NATURAL)

    change_duration(score=score, carrier=chord, rhythmic_value=RhythmicValue.HALF, dots=1)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "0"),
        slot(0, _H, _H, "1,2"),
        slot(1, Fraction(0), _Q, "1,2"),
        *[slot(1, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert tie_layout(score=score) == [
        TieSlot(start=(0, _H, 1), end=(1, Fraction(0), 1)),
        TieSlot(start=(0, _H, 2), end=(1, Fraction(0), 2)),
    ]
    assert note_at(score=score, at=_H).note_carrier is chord
    assert anchor_layout(score=score) == [
        (0, Fraction(0)),
        (0, _Q),
        (0, _H),
        *[(1, Fraction(beat, 4)) for beat in range(4)],
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_a_rest_cut_at_the_barline_leaves_plain_pieces() -> None:
    """A quarter rest on beat three becomes a dotted half rest, cut at the barline.

    The first piece is the same rest resized; the piece after the barline is a new rest.
    """
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(0, 1))
    rest(score=score, parent=score.voice, at=_H, rhythmic_value=RhythmicValue.QUARTER)
    quarters(score=score, measure=0, beats=(3,))
    quarters(score=score, measure=1)
    target: Rest = rest_at(score=score, at=_H)

    change_duration(
        score=score,
        carrier=target.rest_carrier,
        rhythmic_value=RhythmicValue.HALF,
        dots=1,
    )

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "0"),
        slot(0, _H, _H, "rest"),
        slot(1, Fraction(0), _Q, "rest"),
        *[slot(1, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert rest_at(score=score, at=_H) is target
    assert rest_at(score=score, at=Fraction(1)) is not target
    assert tie_layout(score=score) == []
    assert anchor_layout(score=score) == [
        (0, Fraction(0)),
        (0, _Q),
        (0, _H),
        *[(1, Fraction(beat, 4)) for beat in range(4)],
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_a_longer_value_over_a_tied_neighbour_removes_it_with_its_tie() -> None:
    """The quarter on beat three becomes a half and meets the first piece of the tied half.

    That piece goes with its tie; the second piece in measure two stays, untied.
    """
    score: Score = crossing_half()
    target: Note = note_at(score=score, at=_H)
    leaf: LeafRhythmicContainer = _leaf_of(target.note_carrier)

    change_duration(score=score, carrier=target.note_carrier, rhythmic_value=RhythmicValue.HALF)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "0"),
        slot(0, _H, _H, "0"),
        slot(1, Fraction(0), _Q, "1"),
        slot(1, _Q, Fraction(3, 4), "rest"),
    ]
    assert tie_layout(score=score) == []
    assert _leaf_of(target.note_carrier) is leaf
    assert anchor_layout(score=score) == [
        (0, Fraction(0)),
        (0, _Q),
        (0, _H),
        (1, Fraction(0)),
        (1, _Q),
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_a_shorter_value_resizes_the_leaf_and_fill_takes_the_freed_room() -> None:
    score: Score = build_score(measure_count=1)
    note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.HALF,
        step=1,
    )
    quarters(score=score, measure=0, beats=(2, 3))
    target: Note = note_at(score=score, at=Fraction(0))
    leaf: LeafRhythmicContainer = _leaf_of(target.note_carrier)

    change_duration(score=score, carrier=target.note_carrier, rhythmic_value=RhythmicValue.QUARTER)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "1"),
        slot(0, _Q, _Q, "rest"),
        slot(0, _H, _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert note_at(score=score, at=Fraction(0)) is target
    assert _leaf_of(target.note_carrier) is leaf
    assert tie_layout(score=score) == []
    assert anchor_layout(score=score) == [(0, Fraction(beat, 4)) for beat in range(4)]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_lengthening_the_second_piece_of_a_tied_half_keeps_its_incoming_tie() -> None:
    """The start did not move, so the tie into the second piece stays.

    The rest it newly meets goes and fill takes the room after the new half.
    """
    score: Score = crossing_half()
    first: Note = note_at(score=score, at=Fraction(3, 4))
    second: Note = note_at(score=score, at=Fraction(1))
    tie: Tie = find_tie(note_with_tie=first)

    change_duration(score=score, carrier=second.note_carrier, rhythmic_value=RhythmicValue.HALF)

    assert layout(score=score) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        slot(0, Fraction(3, 4), _Q, "1"),
        slot(1, Fraction(0), _H, "1"),
        slot(1, _H, _H, "rest"),
    ]
    assert tie_layout(score=score) == [
        TieSlot(start=(0, Fraction(3, 4), 1), end=(1, Fraction(0), 1))
    ]
    assert find_tie(note_with_tie=second) is tie
    assert anchor_layout(score=score) == [
        *[(0, Fraction(beat, 4)) for beat in range(4)],
        (1, Fraction(0)),
        (1, _H),
    ]
    assert orphan_anchors(score=score) == []


def _tied_quarters() -> Score:
    """Build a quarter tied to the quarter after it (both step 1), then two quarters."""
    score: Score = build_score(measure_count=1)
    note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.QUARTER,
        step=1,
    )
    note(score=score, parent=score.voice, at=_Q, rhythmic_value=RhythmicValue.QUARTER, step=1)
    quarters(score=score, measure=0, beats=(2, 3))
    apply_intent(
        score=score,
        intent=TieNotesIntent(
            start_note_id=note_at(score=score, at=Fraction(0)).id,
            end_note_id=note_at(score=score, at=_Q).id,
        ),
    )

    return score


@pytest.mark.unit
@_PENDING
def test_shortening_a_tied_note_away_from_the_next_note_removes_the_outgoing_tie() -> None:
    """The quarter becomes an eighth and no longer touches the note it was tied to; the tie goes.

    Fill takes the eighth after it; the next note stays.
    """
    score: Score = _tied_quarters()
    target: Note = note_at(score=score, at=Fraction(0))
    next_note: Note = note_at(score=score, at=_Q)

    change_duration(score=score, carrier=target.note_carrier, rhythmic_value=RhythmicValue.EIGHTH)

    assert layout(score=score) == [
        slot(0, Fraction(0), _E, "1"),
        slot(0, _E, _E, "rest"),
        slot(0, _Q, _Q, "1"),
        slot(0, _H, _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert tie_layout(score=score) == []
    assert list(target.relations) == []
    assert note_at(score=score, at=_Q) is next_note
    assert list(next_note.relations) == []
    assert anchor_layout(score=score) == [
        (0, Fraction(0)),
        (0, _E),
        (0, _Q),
        (0, _H),
        (0, Fraction(3, 4)),
    ]
    assert broken_relations(score=score) == []
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_shortening_an_element_away_from_the_next_note_breaks_its_glissando_and_beam() -> None:
    """Four beamed eighths (steps 1-4), a glissando from the second to the third; the second
    becomes a sixteenth and its freed room (filled with a rest) lies before the third.

    The relation guard removes the glissando and cuts the beam there into two of two.
    """
    score: Score = build_score(measure_count=1)
    for index in range(4):
        note(
            score=score,
            parent=score.voice,
            at=index * _E,
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index + 1,
        )
    rest(score=score, parent=score.voice, at=_H, rhythmic_value=RhythmicValue.HALF)
    carriers: list[Carrier] = [
        note_at(score=score, at=index * _E).note_carrier for index in range(4)
    ]
    beam: Beam = Beam.create(carriers=carriers)
    glissando: Glissando = Glissando.create(
        start_note=note_at(score=score, at=_E),
        end_note=note_at(score=score, at=_Q),
        glissando_type=GlissandoType.STRAIGHT,
    )

    change_duration(score=score, carrier=carriers[1], rhythmic_value=RhythmicValue.SIXTEENTH)

    assert layout(score=score) == [
        slot(0, Fraction(0), _E, "1"),
        slot(0, _E, _E / 2, "2"),
        slot(0, 3 * _E / 2, _E / 2, "rest"),
        slot(0, _Q, _E, "3"),
        slot(0, 3 * _E, _E, "4"),
        slot(0, _H, _H, "rest"),
    ]
    assert list(glissando.start.relations) == []
    assert list(glissando.end.relations) == []
    assert [list(found.members) for found in find_beams(carriers=carriers)] == [
        carriers[:2],
        carriers[2:],
    ]
    assert find_beams(carriers=carriers[:1]) == [beam]
    assert broken_relations(score=score) == []
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_lengthening_a_tied_note_over_the_note_it_is_tied_to_removes_that_note() -> None:
    """The quarter becomes a half and meets the note it was tied to; that note goes with the tie."""
    score: Score = _tied_quarters()
    target: Note = note_at(score=score, at=Fraction(0))

    change_duration(score=score, carrier=target.note_carrier, rhythmic_value=RhythmicValue.HALF)

    assert layout(score=score) == [
        slot(0, Fraction(0), _H, "1"),
        slot(0, _H, _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert tie_layout(score=score) == []
    assert note_at(score=score, at=Fraction(0)) is target
    assert list(target.relations) == []
    assert anchor_layout(score=score) == [(0, Fraction(0)), (0, _H), (0, Fraction(3, 4))]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_changing_a_tied_note_to_its_own_value_keeps_the_outgoing_tie() -> None:
    """The element still touches the note it was tied to, so the same tie stays and the
    gesture writes nothing at all."""
    score: Score = _tied_quarters()
    target: Note = note_at(score=score, at=Fraction(0))
    next_note: Note = note_at(score=score, at=_Q)
    tie: Tie = find_tie(note_with_tie=target)
    before: Snapshot = snapshot(score=score)

    log: MutationLog = change_duration(
        score=score,
        carrier=target.note_carrier,
        rhythmic_value=RhythmicValue.QUARTER,
    )

    assert log._entries == []
    assert snapshot(score=score) == before
    assert tie_layout(score=score) == [TieSlot(start=(0, Fraction(0), 1), end=(0, _Q, 1))]
    assert note_at(score=score, at=Fraction(0)) is target
    assert note_at(score=score, at=_Q) is next_note
    assert find_tie(note_with_tie=target) is tie
    assert find_tie(note_with_tie=next_note) is tie
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_a_triplet_note_cut_at_the_barline_stays_in_its_triplet() -> None:
    """The triplet's first quarter (step 1) becomes a triplet half across the barline.

    It meets both eighths of the tied middle quarter, which go with their tie; the same
    leaf is the dotted quarter to the barline and a new tied eighth follows inside the
    triplet.
    """
    score: Score = crossing_triplet()
    target: Note = note_at(score=score, at=Fraction(3, 4))
    leaf: LeafRhythmicContainer = _leaf_of(target.note_carrier)
    groups_before: list[GroupSlot] = group_layout(score=score)

    change_duration(score=score, carrier=target.note_carrier, rhythmic_value=RhythmicValue.HALF)

    assert layout(score=score) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        slot(0, Fraction(3, 4), Fraction(3, 8), "1", depth=1),
        slot(1, Fraction(0), _E, "1", depth=1),
        slot(1, Fraction(1, 12), _Q, "3", depth=1),
        *[slot(1, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert tie_layout(score=score) == [
        TieSlot(start=(0, Fraction(3, 4), 1), end=(1, Fraction(0), 1))
    ]
    assert group_layout(score=score) == groups_before
    assert _leaf_of(target.note_carrier) is leaf
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_a_chord_with_one_tied_note_cut_at_the_barline() -> None:
    """A chord (steps 1, 2) whose step 2 is tied in and step 1 tied out becomes a dotted half.

    The incoming tie stays the same object; the outgoing one goes with the note it met;
    both notes are tied across the barline.
    """
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(0,))
    note(score=score, parent=score.voice, at=_Q, rhythmic_value=RhythmicValue.QUARTER, step=2)
    note(score=score, parent=score.voice, at=_H, rhythmic_value=RhythmicValue.QUARTER, step=1)
    note(
        score=score,
        parent=score.voice,
        at=Fraction(3, 4),
        rhythmic_value=RhythmicValue.QUARTER,
        step=1,
    )
    quarters(score=score, measure=1)
    chord: NoteCarrier = note_at(score=score, at=_H).note_carrier
    lower: Note = chord.notes[0]
    upper: Note = Note.create(
        note_carrier=chord,
        staff=score.staff,
        staff_step=2,
        accidental=Accidental.NATURAL,
    )
    apply_intent(
        score=score,
        intent=TieNotesIntent(start_note_id=note_at(score=score, at=_Q).id, end_note_id=upper.id),
    )
    apply_intent(
        score=score,
        intent=TieNotesIntent(
            start_note_id=lower.id,
            end_note_id=note_at(score=score, at=Fraction(3, 4)).id,
        ),
    )
    incoming: Tie = find_tie(note_with_tie=note_at(score=score, at=_Q))

    change_duration(score=score, carrier=chord, rhythmic_value=RhythmicValue.HALF, dots=1)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "2"),
        slot(0, _H, _H, "1,2"),
        slot(1, Fraction(0), _Q, "1,2"),
        *[slot(1, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert tie_layout(score=score) == [
        TieSlot(start=(0, _Q, 2), end=(0, _H, 2)),
        TieSlot(start=(0, _H, 1), end=(1, Fraction(0), 1)),
        TieSlot(start=(0, _H, 2), end=(1, Fraction(0), 2)),
    ]
    assert any(relation is incoming for relation in upper.relations)
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_lengthening_onto_a_triplet_removes_it_and_fill_takes_the_rest() -> None:
    """The quarter before the triplet becomes a dotted quarter: its frames are cleared, so
    the triplet goes whole, and fill puts an eighth rest in what is left of its room."""
    score: Score = triplet_scene()
    target: Note = note_at(score=score, at=Fraction(0))
    leaf: LeafRhythmicContainer = _leaf_of(target.note_carrier)

    change_duration(
        score=score,
        carrier=target.note_carrier,
        rhythmic_value=RhythmicValue.QUARTER,
        dots=1,
    )

    assert layout(score=score) == [
        slot(0, Fraction(0), Fraction(3, 8), "0"),
        slot(0, Fraction(3, 8), _E, "rest"),
        slot(0, _H, _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert group_layout(score=score) == []
    assert _leaf_of(target.note_carrier) is leaf
    assert anchor_layout(score=score) == [
        (0, Fraction(0)),
        (0, Fraction(3, 8)),
        (0, _H),
        (0, Fraction(3, 4)),
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_undo_and_redo_of_a_cut_restore_each_side_of_the_gesture() -> None:
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(0, 1))
    note(score=score, parent=score.voice, at=_H, rhythmic_value=RhythmicValue.QUARTER, step=1)
    quarters(score=score, measure=0, beats=(3,))
    quarters(score=score, measure=1)
    target: Note = note_at(score=score, at=_H)
    before: Snapshot = snapshot(score=score)

    log: MutationLog = change_duration(
        score=score,
        carrier=target.note_carrier,
        rhythmic_value=RhythmicValue.HALF,
        dots=1,
    )
    after: Snapshot = snapshot(score=score)

    log.rollback()
    assert snapshot(score=score) == before
    assert note_at(score=score, at=_H) is target
    assert orphan_anchors(score=score) == []

    log.reapply()
    assert snapshot(score=score) == after
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_a_longer_rest_resizes_in_place_and_removes_the_note_it_meets() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    rest(score=score, parent=score.voice, at=_Q, rhythmic_value=RhythmicValue.QUARTER)
    quarters(score=score, measure=0, beats=(2, 3))
    target: Rest = rest_at(score=score, at=_Q)
    leaf: LeafRhythmicContainer = _leaf_of(target.rest_carrier)

    change_duration(score=score, carrier=target.rest_carrier, rhythmic_value=RhythmicValue.HALF)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _H, "rest"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert rest_at(score=score, at=_Q) is target
    assert _leaf_of(target.rest_carrier) is leaf
    assert anchor_layout(score=score) == [(0, Fraction(0)), (0, _Q), (0, Fraction(3, 4))]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_a_shorter_rest_resizes_in_place_and_fill_takes_the_freed_room() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    rest(score=score, parent=score.voice, at=_Q, rhythmic_value=RhythmicValue.HALF)
    quarters(score=score, measure=0, beats=(3,))
    target: Rest = rest_at(score=score, at=_Q)
    leaf: LeafRhythmicContainer = _leaf_of(target.rest_carrier)

    change_duration(score=score, carrier=target.rest_carrier, rhythmic_value=RhythmicValue.QUARTER)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "rest"),
        slot(0, _H, _Q, "rest"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert rest_at(score=score, at=_Q) is target
    assert _leaf_of(target.rest_carrier) is leaf
    assert anchor_layout(score=score) == [(0, Fraction(beat, 4)) for beat in range(4)]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
@_PENDING
def test_lengthening_past_the_end_of_the_score_is_refused_and_changes_nothing() -> None:
    score: Score = four_quarters()
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match=_OUT_OF_SCOPE):
        change_duration(
            score=score,
            carrier=note_at(score=score, at=Fraction(3, 4)).note_carrier,
            rhythmic_value=RhythmicValue.HALF,
        )

    assert snapshot(score=score) == before


@pytest.mark.unit
@_PENDING
def test_lengthening_past_the_end_of_its_tuplet_is_refused_and_changes_nothing() -> None:
    """The triplet's last eighth becomes a quarter of the triplet and would leave it; refused."""
    score: Score = triplet_scene()
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match=_OUT_OF_SCOPE):
        change_duration(
            score=score,
            carrier=note_at(score=score, at=_Q + 2 * _THIRD).note_carrier,
            rhythmic_value=RhythmicValue.QUARTER,
        )

    assert snapshot(score=score) == before
