from fractions import Fraction

import pytest
from tests.unit.domain.document_builders import note, score

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import Accidental
from piano_app.domain.score.document.models.relations import Tie
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import (
    ChangePitchIntent,
    EditIntent,
    MoveNoteToStaffIntent,
    PitchEditMode,
    SetAccidentalIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch


def _run(*, document: ScoreDocument, intent: EditIntent) -> MutationLog:
    return build_engine().process(
        document=document,
        requests=build_compiler().compile(document=document, intent=intent),
    )


def _midi(*, document: ScoreDocument, target: Note) -> int:
    """What a note sounds like, read from a fresh index."""
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    pitch: ScorePitch = ScorePitch(
        document=document,
        geometry=geometry,
        contexts=ContextIndex(document=document, geometry=geometry),
    )
    return pitch.pitch_of(note=target).midi_note


def test_a_note_put_on_another_step_keeps_its_staff_accidental_and_identity() -> None:
    document: ScoreDocument = score()
    moved: Note = note(document, Fraction(0), step=-2)
    staff, accidental, carrier = moved.staff, moved.accidental, moved.note_carrier

    log: MutationLog = _run(
        document=document, intent=ChangePitchIntent(note_id=moved.id, staff_step=1)
    )

    assert moved.staff_step == 1
    assert (moved.staff, moved.accidental, moved.note_carrier) == (staff, accidental, carrier)

    log.rollback()
    assert moved.staff_step == -2

    log.reapply()
    assert moved.staff_step == 1


def test_the_note_a_changed_note_is_tied_to_follows_it_and_sounds_the_same() -> None:
    document: ScoreDocument = score()
    first: Note = note(document, Fraction(0), step=-2)
    second: Note = note(document, Fraction(1, 4), step=-2)
    Tie.create(start_note=first, end_note=second)

    log: MutationLog = _run(
        document=document, intent=ChangePitchIntent(note_id=first.id, staff_step=1)
    )

    assert (first.staff_step, second.staff_step) == (1, 1)
    assert _midi(document=document, target=second) == _midi(document=document, target=first)

    log.rollback()
    assert (first.staff_step, second.staff_step) == (-2, -2)


def test_a_change_of_pitch_naming_something_that_is_not_a_note_is_refused() -> None:
    document: ScoreDocument = score()
    untouched: Note = note(document, Fraction(0), step=-2)

    with pytest.raises(MutationRejectedError, match="must be Note"):
        _run(
            document=document,
            intent=ChangePitchIntent(note_id=document.voices[0].id, staff_step=1),
        )

    assert untouched.staff_step == -2


def test_a_sharp_leaves_the_step_and_raises_the_sound_by_a_semitone() -> None:
    document: ScoreDocument = score()
    sharpened: Note = note(document, Fraction(0), step=-2)
    before: int = _midi(document=document, target=sharpened)

    log: MutationLog = _run(
        document=document,
        intent=SetAccidentalIntent(note_id=sharpened.id, accidental=Accidental.SHARP),
    )

    assert (sharpened.staff_step, sharpened.accidental) == (-2, Accidental.SHARP)
    assert _midi(document=document, target=sharpened) == before + 1

    log.rollback()
    assert (sharpened.staff_step, sharpened.accidental) == (-2, Accidental.NATURAL)


def test_the_note_a_sharpened_note_is_tied_to_takes_the_same_accidental() -> None:
    document: ScoreDocument = score()
    first: Note = note(document, Fraction(0), step=-2)
    second: Note = note(document, Fraction(1, 4), step=-2)
    Tie.create(start_note=first, end_note=second)

    _run(
        document=document,
        intent=SetAccidentalIntent(note_id=first.id, accidental=Accidental.SHARP),
    )

    assert second.accidental is Accidental.SHARP
    assert _midi(document=document, target=second) == _midi(document=document, target=first)


def test_a_note_moved_to_another_staff_keeping_its_pitch_takes_the_step_that_sounds_as_before() -> (
    None
):
    document: ScoreDocument = score()
    moved: Note = note(document, Fraction(0), step=-2)
    before: int = _midi(document=document, target=moved)

    log: MutationLog = _run(
        document=document,
        intent=MoveNoteToStaffIntent(
            note_id=moved.id,
            staff_id=document.staffs[1].id,
            mode=PitchEditMode.PRESERVE_PITCH,
        ),
    )

    assert moved.staff is document.staffs[1]
    assert moved.staff_step != -2
    assert _midi(document=document, target=moved) == before

    log.rollback()
    assert (moved.staff is document.staffs[0], moved.staff_step) == (True, -2)

    log.reapply()
    assert moved.staff is document.staffs[1]


def test_moving_a_note_to_another_staff_keeping_its_step_changes_the_sound() -> None:
    document: ScoreDocument = score()
    moved: Note = note(document, Fraction(0), step=-2)
    before: int = _midi(document=document, target=moved)

    _run(
        document=document,
        intent=MoveNoteToStaffIntent(
            note_id=moved.id,
            staff_id=document.staffs[1].id,
            mode=PitchEditMode.PRESERVE_STEP,
        ),
    )

    assert (moved.staff is document.staffs[1], moved.staff_step) == (True, -2)
    assert _midi(document=document, target=moved) != before


def test_the_note_a_moved_note_is_tied_to_stays_on_its_staff_and_sounds_the_same() -> None:
    document: ScoreDocument = score()
    moved: Note = note(document, Fraction(0), step=-2)
    tied: Note = note(document, Fraction(1, 4), step=-2)
    Tie.create(start_note=moved, end_note=tied)

    _run(
        document=document,
        intent=MoveNoteToStaffIntent(
            note_id=moved.id,
            staff_id=document.staffs[1].id,
            mode=PitchEditMode.PRESERVE_STEP,
        ),
    )

    assert tied.staff is document.staffs[0]
    assert _midi(document=document, target=tied) == _midi(document=document, target=moved)


def test_moving_a_note_to_something_that_is_not_a_staff_is_refused() -> None:
    document: ScoreDocument = score()
    untouched: Note = note(document, Fraction(0), step=-2)

    with pytest.raises(MutationRejectedError, match="must be Staff"):
        _run(
            document=document,
            intent=MoveNoteToStaffIntent(
                note_id=untouched.id,
                staff_id=document.voices[0].id,
                mode=PitchEditMode.PRESERVE_PITCH,
            ),
        )

    assert (untouched.staff is document.staffs[0], untouched.staff_step) == (True, -2)
