from fractions import Fraction

import pytest
from tests.unit.domain.document_builders import anchor as anchor_at
from tests.unit.domain.document_builders import note, score
from tests.unit.domain.scene import apply_intent, build_score, rest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import ClefChange
from piano_app.domain.score.document.models.material import Note, NoteCarrier, Rest, RestCarrier
from piano_app.domain.score.document.models.notation import (
    Accidental,
    Clef,
    DottedRhythmicValue,
    GracePlacement,
    GraceType,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceItem,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.helpers import fits, sounding_of, taken_from
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import (
    AddGraceNoteIntent,
    ChangeDurationIntent,
    ChangeGraceTypeIntent,
    EditIntent,
    RemoveGraceNoteIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)


def _value(value: RhythmicValue) -> DottedRhythmicValue:
    return DottedRhythmicValue(value=value)


def _run(*, document: ScoreDocument, intent: EditIntent) -> MutationLog:
    return build_engine().process(
        document=document,
        requests=build_compiler().compile(document=document, intent=intent),
    )


def _host(document: ScoreDocument) -> tuple[Note, LeafRhythmicContainer]:
    """A quarter note on the first beat of the first measure."""
    host: Note = note(document, Fraction(0))
    leaf = host.note_carrier.owner
    assert isinstance(leaf, LeafRhythmicContainer)
    return host, leaf


def _add(
    *,
    document: ScoreDocument,
    host: Note,
    value: RhythmicValue = RhythmicValue.EIGHTH,
    kind: GraceType = GraceType.APPOGGIATURA,
    placement: GracePlacement = GracePlacement.BEFORE,
    after_carrier_id: str | None = None,
) -> MutationLog:
    return _run(
        document=document,
        intent=AddGraceNoteIntent(
            host_carrier_id=host.note_carrier.id,
            placement=placement,
            grace_type=kind,
            written_value=_value(value),
            staff_id=document.staffs[0].id,
            staff_step=2,
            accidental=Accidental.NATURAL,
            after_carrier_id=after_carrier_id,
        ),
    )


def test_a_grace_note_sounds_as_written_unless_it_is_slashed_and_then_a_quarter_of_it() -> None:
    document = score()
    host, leaf = _host(document)
    _add(document=document, host=host, kind=GraceType.APPOGGIATURA)
    group = leaf.grace_before
    assert group is not None

    assert sounding_of(group=group, written=Fraction(1, 8)) == Fraction(1, 8)
    assert taken_from(leaf=leaf) == Fraction(1, 8)

    other = score()
    other_host, other_leaf = _host(other)
    _add(document=other, host=other_host, kind=GraceType.ACCIACCATURA)
    assert taken_from(leaf=other_leaf) == Fraction(1, 32)


def test_a_grace_note_is_added_after_the_one_it_is_told_and_goes_with_an_undo() -> None:
    document = score()
    host, leaf = _host(document)

    _add(document=document, host=host, value=RhythmicValue.SIXTEENTH)
    group = leaf.grace_before
    assert group is not None
    first_carrier = group.grace_items[0].carrier
    assert first_carrier is not None
    log = _add(
        document=document,
        host=host,
        value=RhythmicValue.THIRTY_SECOND,
        after_carrier_id=first_carrier.id,
    )

    assert [item.rhythmic_value.value for item in group.grace_items] == [
        RhythmicValue.SIXTEENTH,
        RhythmicValue.THIRTY_SECOND,
    ]
    first = group.grace_items[0].carrier
    assert first is not None
    assert first.owner is group.grace_items[0]

    log.rollback()
    assert leaf.grace_before is group
    assert len(group.grace_items) == 1


def test_the_grace_notes_cannot_take_all_the_time_of_their_note() -> None:
    document = score()
    host, leaf = _host(document)

    # a quarter gives just under 1/4: seven slashed eighths take 7/32, an eighth one more 8/32
    for _ in range(7):
        _add(document=document, host=host, value=RhythmicValue.EIGHTH, kind=GraceType.ACCIACCATURA)
    assert taken_from(leaf=leaf) == Fraction(7, 32)
    assert fits(leaf=leaf, length=Fraction(1, 4))

    with pytest.raises(MutationRejectedError, match="all the time"):
        _add(document=document, host=host, value=RhythmicValue.EIGHTH, kind=GraceType.ACCIACCATURA)

    assert len(leaf.grace_before.grace_items if leaf.grace_before else ()) == 7


def test_the_groups_before_and_after_a_note_take_from_it_together() -> None:
    document = score()
    host, leaf = _host(document)
    _add(document=document, host=host, value=RhythmicValue.EIGHTH)
    _add(
        document=document, host=host, value=RhythmicValue.SIXTEENTH, placement=GracePlacement.AFTER
    )
    assert taken_from(leaf=leaf) == Fraction(3, 16)

    with pytest.raises(MutationRejectedError, match="all the time"):
        _add(
            document=document,
            host=host,
            value=RhythmicValue.SIXTEENTH,
            placement=GracePlacement.AFTER,
        )


def test_the_grace_notes_of_one_group_are_all_of_one_kind() -> None:
    document = score()
    host, _leaf = _host(document)
    _add(document=document, host=host, kind=GraceType.APPOGGIATURA, value=RhythmicValue.SIXTEENTH)

    with pytest.raises(MutationRejectedError, match="one kind"):
        _add(
            document=document,
            host=host,
            kind=GraceType.ACCIACCATURA,
            value=RhythmicValue.SIXTEENTH,
        )


def test_removing_the_last_grace_note_removes_its_group() -> None:
    document = score()
    host, leaf = _host(document)
    _add(document=document, host=host, value=RhythmicValue.SIXTEENTH)
    _add(document=document, host=host, value=RhythmicValue.SIXTEENTH)
    group = leaf.grace_before
    assert group is not None
    graces = [item.carrier.notes[0] for item in group.grace_items if item.carrier is not None]

    _run(document=document, intent=RemoveGraceNoteIntent(note_id=graces[0].id))
    assert leaf.grace_before is group
    assert len(group.grace_items) == 1

    log = _run(document=document, intent=RemoveGraceNoteIntent(note_id=graces[1].id))
    assert leaf.grace_before is None

    log.rollback()
    assert leaf.grace_before is not None


def test_a_note_cannot_be_shortened_below_the_time_its_grace_notes_take() -> None:
    document = score()
    host, leaf = _host(document)
    _add(document=document, host=host, value=RhythmicValue.EIGHTH)

    with pytest.raises(MutationRejectedError, match="no longer fit"):
        _run(
            document=document,
            intent=ChangeDurationIntent(
                carrier_id=host.note_carrier.id, written_value=_value(RhythmicValue.EIGHTH)
            ),
        )

    assert leaf.occupied_size.fraction == Fraction(1, 4)


def test_deleting_a_note_deletes_its_grace_notes_with_it() -> None:
    document = score()
    host, leaf = _host(document)
    _add(document=document, host=host)
    _add(
        document=document, host=host, value=RhythmicValue.SIXTEENTH, placement=GracePlacement.AFTER
    )

    build_engine().process(document=document, requests=[DeleteRequest(target=leaf)])

    assert leaf.grace_before is None
    assert leaf.grace_after is None


def _first_grace_note_id(leaf: LeafRhythmicContainer) -> str:
    group = leaf.grace_before
    assert group is not None
    carrier = group.grace_items[0].carrier
    assert carrier is not None
    return carrier.notes[0].id


def test_a_group_changes_from_plain_to_slashed_and_back_with_the_time_it_takes() -> None:
    document = score()
    host, leaf = _host(document)
    _add(document=document, host=host, value=RhythmicValue.EIGHTH, kind=GraceType.APPOGGIATURA)
    group = leaf.grace_before
    assert group is not None
    note_id = _first_grace_note_id(leaf)
    assert taken_from(leaf=leaf) == Fraction(1, 8)

    log = _run(
        document=document,
        intent=ChangeGraceTypeIntent(note_id=note_id, grace_type=GraceType.ACCIACCATURA),
    )
    assert group.grace_type is GraceType.ACCIACCATURA
    assert taken_from(leaf=leaf) == Fraction(1, 32)

    log.rollback()
    assert group.grace_type is GraceType.APPOGGIATURA
    assert taken_from(leaf=leaf) == Fraction(1, 8)


def test_a_group_cannot_become_plain_when_its_notes_would_take_all_the_time_of_their_note() -> None:
    document = score()
    host, leaf = _host(document)
    for _ in range(3):
        _add(document=document, host=host, value=RhythmicValue.EIGHTH, kind=GraceType.ACCIACCATURA)
    group = leaf.grace_before
    assert group is not None

    # three slashed eighths take 3/32 of a quarter, three plain ones 3/8
    with pytest.raises(MutationRejectedError, match="all the time"):
        _run(
            document=document,
            intent=ChangeGraceTypeIntent(
                note_id=_first_grace_note_id(leaf), grace_type=GraceType.APPOGGIATURA
            ),
        )

    assert group.grace_type is GraceType.ACCIACCATURA


def test_the_kind_of_a_group_is_set_through_one_of_its_grace_notes_only() -> None:
    document = score()
    host, _leaf = _host(document)

    with pytest.raises(MutationRejectedError, match="not a grace note"):
        _run(
            document=document,
            intent=ChangeGraceTypeIntent(note_id=host.id, grace_type=GraceType.ACCIACCATURA),
        )


def _leaf_at(document: ScoreDocument, *, measure: int, position: Fraction) -> LeafRhythmicContainer:
    for anchor in document.measures[measure].anchors:
        if anchor.position.value == position:
            for container in anchor.containers:
                if isinstance(container, LeafRhythmicContainer):
                    return container

    raise LookupError("No leaf there.")


def test_a_cut_note_keeps_the_grace_notes_before_and_gives_the_ones_after_to_its_last_piece() -> (
    None
):
    document = score()
    host: Note = note(document, Fraction(3, 4))
    leaf = host.note_carrier.owner
    assert isinstance(leaf, LeafRhythmicContainer)
    _add(document=document, host=host, value=RhythmicValue.SIXTEENTH)
    _add(
        document=document,
        host=host,
        value=RhythmicValue.EIGHTH,
        kind=GraceType.ACCIACCATURA,
        placement=GracePlacement.AFTER,
    )
    before = leaf.grace_before

    log = _run(
        document=document,
        intent=ChangeDurationIntent(
            carrier_id=host.note_carrier.id, written_value=_value(RhythmicValue.HALF)
        ),
    )

    last = _leaf_at(document, measure=1, position=Fraction(0))
    assert leaf.grace_before is before
    assert leaf.grace_after is None
    assert last.grace_before is None
    moved = last.grace_after
    assert moved is not None
    assert moved.grace_type is GraceType.ACCIACCATURA
    (item,) = moved.grace_items
    assert item.rhythmic_value == _value(RhythmicValue.EIGHTH)
    assert isinstance(item.carrier, NoteCarrier)
    (written,) = item.carrier.notes
    assert (written.staff_step, written.accidental) == (2, Accidental.NATURAL)

    log.rollback()
    assert leaf.grace_after is not None
    assert leaf.grace_before is before


def test_a_grace_note_moved_to_the_last_piece_keeps_its_sound_in_the_clef_there() -> None:
    document = score()
    ClefChange.create(
        start=anchor_at(document, Fraction(1)), staff=document.staffs[0], clef=Clef.BASS
    )
    host: Note = note(document, Fraction(3, 4))
    _add(
        document=document,
        host=host,
        value=RhythmicValue.SIXTEENTH,
        placement=GracePlacement.AFTER,
    )

    _run(
        document=document,
        intent=ChangeDurationIntent(
            carrier_id=host.note_carrier.id, written_value=_value(RhythmicValue.HALF)
        ),
    )

    moved = _leaf_at(document, measure=1, position=Fraction(0)).grace_after
    assert moved is not None
    (item,) = moved.grace_items
    assert isinstance(item.carrier, NoteCarrier)
    (written,) = item.carrier.notes
    # step 2 of the treble clef sounds as step 14 of the bass clef
    assert (written.staff_step, written.accidental) == (14, Accidental.NATURAL)


def test_a_cut_is_refused_when_the_last_piece_cannot_give_the_grace_notes_after_their_time() -> (
    None
):
    document = score()
    host: Note = note(document, Fraction(1, 2), value=RhythmicValue.HALF)
    leaf = host.note_carrier.owner
    assert isinstance(leaf, LeafRhythmicContainer)
    for _ in range(3):
        _add(
            document=document, host=host, value=RhythmicValue.EIGHTH, placement=GracePlacement.AFTER
        )
    group = leaf.grace_after

    # the dotted half leaves a quarter in the next measure: 3/8 of grace notes do not fit there
    with pytest.raises(MutationRejectedError, match="all the time"):
        _run(
            document=document,
            intent=ChangeDurationIntent(
                carrier_id=host.note_carrier.id,
                written_value=DottedRhythmicValue(value=RhythmicValue.HALF, dots_count=1),
            ),
        )

    assert leaf.grace_after is group
    assert leaf.occupied_size.fraction == Fraction(1, 2)


def test_a_cut_rest_gives_its_grace_notes_after_to_its_last_piece() -> None:
    scene = build_score(measure_count=2)
    leaf = rest(
        score=scene, parent=scene.voice, at=Fraction(3, 4), rhythmic_value=RhythmicValue.QUARTER
    )
    carrier = leaf.carrier
    assert carrier is not None
    apply_intent(
        score=scene,
        intent=AddGraceNoteIntent(
            host_carrier_id=carrier.id,
            placement=GracePlacement.AFTER,
            grace_type=GraceType.APPOGGIATURA,
            written_value=_value(RhythmicValue.SIXTEENTH),
            staff_id=scene.staff.id,
            staff_step=2,
            accidental=Accidental.NATURAL,
        ),
    )

    apply_intent(
        score=scene,
        intent=ChangeDurationIntent(
            carrier_id=carrier.id, written_value=_value(RhythmicValue.HALF)
        ),
    )

    last = _leaf_at(scene.document, measure=1, position=Fraction(0))
    assert leaf.grace_after is None
    assert last is not leaf
    assert last.grace_after is not None


def test_a_cut_moves_a_rest_of_the_grace_notes_after_with_them() -> None:
    document = score()
    host: Note = note(document, Fraction(1, 2), value=RhythmicValue.HALF)
    leaf = host.note_carrier.owner
    assert isinstance(leaf, LeafRhythmicContainer)
    _add(
        document=document, host=host, value=RhythmicValue.SIXTEENTH, placement=GracePlacement.AFTER
    )
    group = leaf.grace_after
    assert group is not None
    silent = GraceItem.create(
        grace_group=group, rhythmic_value=DottedRhythmicValue(value=RhythmicValue.SIXTEENTH)
    )
    Rest.create(rest_carrier=RestCarrier.create(owner=silent), staff=host.staff)

    _run(
        document=document,
        intent=ChangeDurationIntent(
            carrier_id=host.note_carrier.id,
            written_value=DottedRhythmicValue(value=RhythmicValue.HALF, dots_count=1),
        ),
    )

    last = _leaf_at(document, measure=1, position=Fraction(0))
    assert leaf.grace_after is None
    assert last.grace_after is not None
    note_item, rest_item = last.grace_after.grace_items
    assert isinstance(note_item.carrier, NoteCarrier)
    assert isinstance(rest_item.carrier, RestCarrier)
    assert rest_item.carrier.rest is not None
    assert rest_item.carrier.rest.staff is host.staff
    assert rest_item.rhythmic_value == DottedRhythmicValue(value=RhythmicValue.SIXTEENTH)
