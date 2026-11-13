from fractions import Fraction

import pytest

from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.models.context import (
    ClefChange,
    KeySignatureChange,
    OctaveTransposition,
)
from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import (
    Accidental,
    Clef,
    DottedRhythmicValue,
    RhythmicSize,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural import MeasurePosition, Staff, TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry import Point
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.pitch import SignCell
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch


def anchor(document: ScoreDocument, at: Fraction) -> TemporalAnchor:
    measure = document.measures[int(at)]
    position = MeasurePosition(value=at - int(at))
    return next(
        (a for a in measure.anchors if a.position == position), None
    ) or TemporalAnchor.create(measure=measure, position=position)


def key(
    document: ScoreDocument, at: Fraction, signs: tuple[Accidental, ...], staff: int = 0
) -> None:
    start = anchor(document, at)
    for context in tuple(start.starting_contexts):
        if isinstance(context, KeySignatureChange) and context.staff is document.staffs[staff]:
            context.detach()
    KeySignatureChange.create(start=start, staff=document.staffs[staff], alterations=signs)


def note(
    document: ScoreDocument,
    at: Fraction,
    sign: Accidental,
    *,
    step: int = -2,
    staff: int = 0,
    voice: int = 0,
    parent: GroupRhythmicContainer | None = None,
) -> Note:
    leaf = LeafRhythmicContainer.create(
        parent=document.voices[voice] if parent is None else parent,
        anchor=anchor(document, at),
        size=RhythmicSize(value=DottedRhythmicValue(value=RhythmicValue.SIXTEENTH), count=1),
    )
    return Note.create(
        note_carrier=NoteCarrier.create(owner=leaf),
        staff=document.staffs[staff],
        staff_step=step,
        accidental=sign,
    )


def infer(
    document: ScoreDocument,
    at: Fraction,
    *,
    step: int = -2,
    staff: int = 0,
    cell: SignCell = SignCell.NOTE,
) -> Accidental:
    geometry = ScoreGeometry(document=document)
    return ScorePitch(
        document=document,
        geometry=geometry,
        contexts=ContextIndex(document=document, geometry=geometry),
    ).accidental_at(
        staff=document.staffs[staff],
        point=Point(frame=geometry.root, value=at),
        staff_step=step,
        cell=cell,
    )


@pytest.mark.parametrize("staff", [0, 1])
@pytest.mark.parametrize("index", range(7))
@pytest.mark.parametrize("octave", [-1, 0, 1])
def test_key_entry_uses_active_clef_and_repeats_every_seven_steps(
    staff: int,
    index: int,
    octave: int,
) -> None:
    document = ScoreDocument.create_fresh(staff_count=2, voice_count=2, measure_count=2)
    signs = tuple(Accidental.SHARP if i == index else Accidental.NATURAL for i in range(7))
    key(document, Fraction(0), signs, staff)
    step = (-2 if staff == 0 else -4) + index + 7 * octave
    assert infer(document, Fraction(0), step=step, staff=staff) is Accidental.SHARP
    assert infer(document, Fraction(0), step=step + 1, staff=staff) is Accidental.NATURAL


def test_latest_matching_line_across_voices_wins_not_collection_order() -> None:
    document = ScoreDocument.create_fresh(staff_count=2, voice_count=3, measure_count=2)
    note(document, Fraction(1, 2), Accidental.FLAT, voice=2)
    note(document, Fraction(1, 4), Accidental.SHARP, voice=1)
    note(document, Fraction(0), Accidental.NATURAL)
    assert infer(document, Fraction(3, 4)) is Accidental.FLAT
    assert infer(document, Fraction(3, 8)) is Accidental.SHARP


def test_local_sign_has_priority_over_changed_key_and_natural_resets_it() -> None:
    document = ScoreDocument.create_fresh(staff_count=2, voice_count=2, measure_count=2)
    note(document, Fraction(0), Accidental.FLAT)
    key(document, Fraction(1, 4), (Accidental.SHARP,) * 7)
    assert infer(document, Fraction(3, 8)) is Accidental.FLAT
    note(document, Fraction(1, 2), Accidental.NATURAL, voice=1)
    assert infer(document, Fraction(3, 4)) is Accidental.NATURAL
    assert infer(document, Fraction(1)) is Accidental.SHARP


def test_a_double_accidental_carries_to_the_barline_and_no_further() -> None:
    document = ScoreDocument.create_fresh(staff_count=2, voice_count=2, measure_count=2)
    note(document, Fraction(0), Accidental.DOUBLE_SHARP)
    assert infer(document, Fraction(1, 2)) is Accidental.DOUBLE_SHARP
    assert infer(document, Fraction(1)) is Accidental.NATURAL


def test_other_staff_steps_and_nonpreceding_notes_do_not_supply_local_sign() -> None:
    document = ScoreDocument.create_fresh(staff_count=2, voice_count=2, measure_count=2)
    note(document, Fraction(0), Accidental.SHARP, staff=1)
    note(document, Fraction(0), Accidental.SHARP, step=5)
    note(document, Fraction(0), Accidental.SHARP, step=-1, voice=1)
    note(document, Fraction(1, 2), Accidental.SHARP)
    note(document, Fraction(3, 4), Accidental.FLAT)
    assert infer(document, Fraction(1, 4)) is Accidental.NATURAL


def test_a_note_reads_the_notes_of_other_voices_standing_on_its_own_anchor() -> None:
    document = ScoreDocument.create_fresh(staff_count=2, voice_count=2, measure_count=2)
    note(document, Fraction(1, 2), Accidental.SHARP, voice=1)
    assert infer(document, Fraction(1, 2)) is Accidental.SHARP


def test_copies_found_previous_note_without_comparing_signs_across_voices() -> None:
    document = ScoreDocument.create_fresh(staff_count=2, voice_count=3, measure_count=2)
    note(document, Fraction(0), Accidental.SHARP)
    note(document, Fraction(0), Accidental.FLAT, voice=1)
    assert infer(document, Fraction(1, 4)) is Accidental.SHARP
    note(document, Fraction(1, 2), Accidental.NATURAL, voice=2)
    assert infer(document, Fraction(3, 4)) is Accidental.NATURAL


def test_same_prior_sign_across_voices_is_unambiguous() -> None:
    document = ScoreDocument.create_fresh(staff_count=2, voice_count=2, measure_count=2)
    note(document, Fraction(0), Accidental.SHARP)
    note(document, Fraction(0), Accidental.SHARP, voice=1)
    assert infer(document, Fraction(1, 4)) is Accidental.SHARP


def test_active_clef_changes_key_mapping_but_octave_shifts_do_not() -> None:
    document = ScoreDocument.create_fresh(staff_count=2, voice_count=2, measure_count=2)
    signs = (
        Accidental.NATURAL,
        Accidental.NATURAL,
        Accidental.FLAT,
        Accidental.NATURAL,
        Accidental.SHARP,
        Accidental.NATURAL,
        Accidental.NATURAL,
    )
    key(document, Fraction(0), signs)
    ClefChange.create(
        start=anchor(document, Fraction(1, 4)),
        staff=document.staffs[0],
        clef=Clef.BASS,
        octave_transposition=2,
    )
    OctaveTransposition.create(
        start=anchor(document, Fraction(0)),
        end=anchor(document, Fraction(1)),
        staff=document.staffs[0],
        octaves=-1,
    )
    assert infer(document, Fraction(0), step=0) is Accidental.FLAT
    assert infer(document, Fraction(1, 4), step=0) is Accidental.SHARP


def test_local_line_is_staff_step_even_after_clef_changes() -> None:
    document = ScoreDocument.create_fresh(staff_count=2, voice_count=2, measure_count=2)
    note(document, Fraction(0), Accidental.FLAT, step=0)
    ClefChange.create(
        start=anchor(document, Fraction(1, 4)), staff=document.staffs[0], clef=Clef.BASS
    )
    assert infer(document, Fraction(1, 2), step=0) is Accidental.FLAT


def test_nested_group_notes_keep_global_anchor_order() -> None:
    document = ScoreDocument.create_fresh(staff_count=2, voice_count=2, measure_count=2)
    group = GroupRhythmicContainer.create(
        parent=document.voices[1],
        anchor=anchor(document, Fraction(0)),
        written_size=RhythmicSize(value=DottedRhythmicValue(value=RhythmicValue.EIGHTH), count=3),
        occupied_size=RhythmicSize(value=DottedRhythmicValue(value=RhythmicValue.QUARTER), count=1),
    )
    inner = GroupRhythmicContainer.create(
        parent=group,
        anchor=anchor(document, Fraction(0)),
        written_size=RhythmicSize(
            value=DottedRhythmicValue(value=RhythmicValue.SIXTEENTH), count=3
        ),
        occupied_size=RhythmicSize(value=DottedRhythmicValue(value=RhythmicValue.EIGHTH), count=1),
    )
    note(document, Fraction(1, 36), Accidental.FLAT, voice=1, parent=inner)
    assert infer(document, Fraction(1, 18)) is Accidental.FLAT


def test_inference_reads_the_notes_and_the_key_the_indexes_were_told_of() -> None:
    document = ScoreDocument.create_fresh(staff_count=2, voice_count=2, measure_count=2)
    geometry = ScoreGeometry(document=document)
    contexts = ContextIndex(document=document, geometry=geometry)
    pitch = ScorePitch(document=document, geometry=geometry, contexts=contexts)
    point = Point(frame=geometry.root, value=Fraction(1, 2))
    assert (
        pitch.accidental_at(
            staff=document.staffs[0], point=point, staff_step=-2, cell=SignCell.NOTE
        )
        is Accidental.NATURAL
    )
    key(document, Fraction(0), (Accidental.SHARP,) * 7)
    # the key comes from the context index, told of a new context; the notes from the pitch index
    contexts.invalidate_measures()
    assert (
        pitch.accidental_at(
            staff=document.staffs[0], point=point, staff_step=-2, cell=SignCell.NOTE
        )
        is Accidental.SHARP
    )
    previous = note(document, Fraction(0), Accidental.FLAT)
    pitch.invalidate_note(note=previous)
    assert (
        pitch.accidental_at(
            staff=document.staffs[0], point=point, staff_step=-2, cell=SignCell.NOTE
        )
        is Accidental.FLAT
    )
    previous.set_accidental(accidental=Accidental.NATURAL)
    pitch.invalidate_note(note=previous)
    assert (
        pitch.accidental_at(
            staff=document.staffs[0], point=point, staff_step=-2, cell=SignCell.NOTE
        )
        is Accidental.NATURAL
    )


def test_absent_key_is_natural_and_bounds_and_staff_are_checked() -> None:
    document = ScoreDocument.create_fresh(staff_count=2, voice_count=2, measure_count=2)
    for context in tuple(document.staffs[0].contexts):
        if isinstance(context, KeySignatureChange):
            context.detach()
    assert infer(document, Fraction(0)) is Accidental.NATURAL
    geometry = ScoreGeometry(document=document)
    contexts = ContextIndex(document=document, geometry=geometry)
    pitch = ScorePitch(document=document, geometry=geometry, contexts=contexts)
    with pytest.raises(ValueError, match="outside"):
        pitch.accidental_at(
            staff=document.staffs[0],
            point=Point(frame=geometry.root, value=Fraction(2)),
            staff_step=0,
            cell=SignCell.NOTE,
        )
    with pytest.raises(ValueError, match="Staff"):
        pitch.accidental_at(
            staff=Staff(),
            point=Point(frame=geometry.root, value=Fraction(0)),
            staff_step=0,
            cell=SignCell.NOTE,
        )
