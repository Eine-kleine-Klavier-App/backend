from fractions import Fraction

import pytest
from tests.unit.domain.document_builders import note, score

from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import Accidental
from piano_app.domain.score.document.models.relations import Tie
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import ShiftStaffStepsIntent
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError


@pytest.mark.parametrize("delta", [-1, 1])
@pytest.mark.parametrize("reverse", [False, True])
def test_group_shift_is_relative_atomic_and_keeps_accidentals_positions_and_identity(
    delta, reverse
):
    document = score()
    first = note(document, Fraction(0), step=-2)
    second = Note.create(
        note_carrier=first.note_carrier,
        staff=first.staff,
        staff_step=-1,
        accidental=Accidental.NATURAL,
    )
    third = note(document, Fraction(1, 4), staff=1, voice=1, step=3)
    third.set_accidental(accidental=Accidental.FLAT)
    engine = build_engine()
    engine.process(document=document, requests=[])
    geometry = ScoreGeometry(document=document)
    selected = [first, second, third]
    before = [
        (n.id, n.staff, n.staff_step, n.accidental, n.note_carrier, n.note_carrier.owner)
        for n in selected
    ]
    spans = [geometry.global_span_of(container=n.note_carrier.owner) for n in selected]
    ids = [n.id for n in selected]
    if reverse:
        ids.reverse()
    requests = build_compiler().compile(
        document=document, intent=ShiftStaffStepsIntent(note_ids=tuple(ids + ids), delta=delta)
    )
    assert len(requests) == 3
    log = engine.process(document=document, requests=requests)
    assert [n.staff_step for n in selected] == [-2 + delta, -1 + delta, 3 + delta]
    assert [
        (n.id, n.staff, n.accidental, n.note_carrier, n.note_carrier.owner) for n in selected
    ] == [
        (id, staff, accidental, carrier, owner)
        for id, staff, step, accidental, carrier, owner in before
    ]
    assert [
        ScoreGeometry(document=document).global_span_of(container=n.note_carrier.owner)
        for n in selected
    ] == spans
    log.rollback()
    assert [n.staff_step for n in selected] == [-2, -1, 3]
    log.reapply()
    assert [n.staff_step for n in selected] == [-2 + delta, -1 + delta, 3 + delta]


@pytest.mark.parametrize("both", [False, True])
def test_tie_chain_moves_once_and_rolls_back_together(both):
    document = score()
    a = note(document, Fraction(0))
    b = note(document, Fraction(1, 4))
    tie = Tie.create(start_note=a, end_note=b)
    engine = build_engine()
    engine.process(document=document, requests=[])
    requests = build_compiler().compile(
        document=document,
        intent=ShiftStaffStepsIntent(note_ids=(a.id, b.id) if both else (a.id,), delta=1),
    )
    log = engine.process(document=document, requests=requests)
    assert (a.staff_step, b.staff_step) == (-1, -1)
    assert tie.start is a and tie.end is b
    log.rollback()
    assert (a.staff_step, b.staff_step) == (-2, -2)


def test_collision_rolls_back_every_selected_note():
    document = score()
    a = note(document, Fraction(0), step=-2)
    Note.create(
        note_carrier=a.note_carrier, staff=a.staff, staff_step=-1, accidental=Accidental.NATURAL
    )
    b = note(document, Fraction(1, 4), step=4)
    engine = build_engine()
    engine.process(document=document, requests=[])
    requests = build_compiler().compile(
        document=document, intent=ShiftStaffStepsIntent(note_ids=(b.id, a.id), delta=1)
    )
    with pytest.raises(MutationRejectedError):
        engine.process(document=document, requests=requests)
    assert (a.staff_step, b.staff_step) == (-2, 4)


@pytest.mark.parametrize("bad", ["empty", "missing", "carrier", "zero", "large"])
def test_bad_selection_or_delta_is_rejected_before_mutation(bad):
    document = score()
    a = note(document, Fraction(0))
    ids = (
        ()
        if bad == "empty"
        else (a.id, "missing")
        if bad == "missing"
        else (a.note_carrier.id,)
        if bad == "carrier"
        else (a.id,)
    )
    delta = 0 if bad == "zero" else 2 if bad == "large" else 1
    with pytest.raises(MutationRejectedError):
        build_compiler().compile(
            document=document, intent=ShiftStaffStepsIntent(note_ids=ids, delta=delta)
        )
    assert a.staff_step == -2


@pytest.mark.parametrize("delta", [-1, 1])
@pytest.mark.parametrize("duplicate_id", [False, True])
def test_single_note_skips_one_unison_and_history_preserves_the_chord(delta, duplicate_id):
    document = score()
    moving = note(document, Fraction(0), step=-2)
    stationary = Note.create(
        note_carrier=moving.note_carrier,
        staff=moving.staff,
        staff_step=-2 + delta,
        accidental=Accidental.NATURAL,
    )
    engine = build_engine()
    engine.process(document=document, requests=[])
    requests = build_compiler().compile(
        document=document,
        intent=ShiftStaffStepsIntent(
            note_ids=(moving.id, moving.id) if duplicate_id else (moving.id,), delta=delta
        ),
    )
    assert moving.staff_step == -2
    log = engine.process(document=document, requests=requests)
    assert moving.staff_step == -2 + 2 * delta
    assert stationary.staff_step == -2 + delta
    assert moving.accidental is Accidental.NATURAL
    log.rollback()
    assert moving.staff_step == -2
    log.reapply()
    assert moving.staff_step == -2 + 2 * delta


@pytest.mark.parametrize("delta", [-1, 1])
def test_second_step_is_not_skipped_again_when_also_occupied(delta):
    document = score()
    moving = note(document, Fraction(0), step=-2)
    for distance in (1, 2):
        Note.create(
            note_carrier=moving.note_carrier,
            staff=moving.staff,
            staff_step=-2 + distance * delta,
            accidental=Accidental.NATURAL,
        )
    engine = build_engine()
    engine.process(document=document, requests=[])
    requests = build_compiler().compile(
        document=document, intent=ShiftStaffStepsIntent(note_ids=(moving.id,), delta=delta)
    )
    with pytest.raises(MutationRejectedError):
        engine.process(document=document, requests=requests)
    assert moving.staff_step == -2


@pytest.mark.parametrize(
    "other_accidental, expected", [(Accidental.NATURAL, -1), (Accidental.SHARP, 0)]
)
def test_skip_uses_sounding_pitch_instead_of_staff_step(other_accidental, expected):
    document = score()
    moving = note(document, Fraction(0), step=-2)
    moving.set_accidental(accidental=Accidental.SHARP)
    Note.create(
        note_carrier=moving.note_carrier,
        staff=moving.staff,
        staff_step=-1,
        accidental=other_accidental,
    )
    engine = build_engine()
    engine.process(document=document, requests=[])
    log = engine.process(
        document=document,
        requests=build_compiler().compile(
            document=document, intent=ShiftStaffStepsIntent(note_ids=(moving.id,), delta=1)
        ),
    )
    assert moving.staff_step == expected
    assert moving.accidental is Accidental.SHARP
    log.rollback()
    assert moving.staff_step == -2


def test_enharmonic_collision_on_different_staff_step_is_skipped():
    document = score()
    moving = note(document, Fraction(0), step=-2)
    moving.set_accidental(accidental=Accidental.SHARP)
    Note.create(
        note_carrier=moving.note_carrier,
        staff=moving.staff,
        staff_step=0,
        accidental=Accidental.FLAT,
    )
    engine = build_engine()
    engine.process(document=document, requests=[])
    engine.process(
        document=document,
        requests=build_compiler().compile(
            document=document, intent=ShiftStaffStepsIntent(note_ids=(moving.id,), delta=1)
        ),
    )
    assert moving.staff_step == 0
    assert moving.accidental is Accidental.SHARP


def test_skip_propagates_along_tie_and_undo_restores_both():
    document = score()
    moving = note(document, Fraction(0), step=-2)
    tied = note(document, Fraction(1, 4), step=-2)
    tie = Tie.create(start_note=moving, end_note=tied)
    Note.create(
        note_carrier=moving.note_carrier,
        staff=moving.staff,
        staff_step=-1,
        accidental=Accidental.NATURAL,
    )
    engine = build_engine()
    engine.process(document=document, requests=[])
    log = engine.process(
        document=document,
        requests=build_compiler().compile(
            document=document, intent=ShiftStaffStepsIntent(note_ids=(moving.id,), delta=1)
        ),
    )
    assert (moving.staff_step, tied.staff_step) == (0, 0)
    assert tie.start is moving and tie.end is tied
    log.rollback()
    assert (moving.staff_step, tied.staff_step) == (-2, -2)


def test_unison_on_other_staff_of_same_chord_is_skipped():
    document = score()
    moving = note(document, Fraction(0), step=-2)
    Note.create(
        note_carrier=moving.note_carrier,
        staff=document.staffs[1],
        staff_step=11,
        accidental=Accidental.NATURAL,
    )
    engine = build_engine()
    engine.process(document=document, requests=[])
    engine.process(
        document=document,
        requests=build_compiler().compile(
            document=document, intent=ShiftStaffStepsIntent(note_ids=(moving.id,), delta=1)
        ),
    )
    assert moving.staff_step == 0


def test_collision_on_tied_chord_still_rejects_and_restores_the_entire_gesture():
    document = score()
    moving = note(document, Fraction(0), step=-2)
    tied = note(document, Fraction(1, 4), step=-2)
    Tie.create(start_note=moving, end_note=tied)
    for carrier, step in [(moving.note_carrier, -1), (tied.note_carrier, 0)]:
        Note.create(
            note_carrier=carrier,
            staff=moving.staff,
            staff_step=step,
            accidental=Accidental.NATURAL,
        )
    engine = build_engine()
    engine.process(document=document, requests=[])
    requests = build_compiler().compile(
        document=document, intent=ShiftStaffStepsIntent(note_ids=(moving.id,), delta=1)
    )
    with pytest.raises(MutationRejectedError):
        engine.process(document=document, requests=requests)
    assert (moving.staff_step, tied.staff_step) == (-2, -2)
