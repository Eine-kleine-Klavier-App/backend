from fractions import Fraction

from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    GracePlacement,
    GraceType,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceGroup,
    GraceItem,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry import Point
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.pitch import SignCell
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch

from .test_accidental_inference import infer, note

_NATURAL = Accidental.NATURAL
_SHARP = Accidental.SHARP
_FLAT = Accidental.FLAT


def grace(document: ScoreDocument, host: Note, placement: GracePlacement, sign: Accidental) -> Note:
    leaf = host.note_carrier.owner
    assert isinstance(leaf, LeafRhythmicContainer)
    group = leaf.grace_before if placement is GracePlacement.BEFORE else leaf.grace_after
    if group is None:
        group = GraceGroup.create(leaf=leaf, grace_type=GraceType.APPOGGIATURA, placement=placement)

    item = GraceItem.create(
        grace_group=group, rhythmic_value=DottedRhythmicValue(value=RhythmicValue.SIXTEENTH)
    )
    return Note.create(
        note_carrier=NoteCarrier.create(owner=item),
        staff=document.staffs[0],
        staff_step=-2,
        accidental=sign,
    )


def two_voices() -> ScoreDocument:
    """One measure, every note and grace note on one line, signs as the rule gives them.

    Voice 0: A (0) with a grace note before (natural) and one after (sharp), D (1/2) with one
    after (natural). Voice 1: B (0), C (1/4), E (1/2), I (5/8) with one before (flat), G (3/4).
    """
    document = ScoreDocument.create_fresh(staff_count=2, voice_count=2, measure_count=2)
    a = note(document, Fraction(0), _NATURAL)
    grace(document, a, GracePlacement.BEFORE, _NATURAL)
    grace(document, a, GracePlacement.AFTER, _SHARP)
    note(document, Fraction(0), _NATURAL, voice=1)
    note(document, Fraction(1, 4), _SHARP, voice=1)
    d = note(document, Fraction(1, 2), _SHARP)
    grace(document, d, GracePlacement.AFTER, _NATURAL)
    note(document, Fraction(1, 2), _SHARP, voice=1)
    i = note(document, Fraction(5, 8), _FLAT, voice=1)
    grace(document, i, GracePlacement.BEFORE, _FLAT)
    note(document, Fraction(3, 4), _FLAT, voice=1)
    return document


def test_a_note_reads_the_grace_notes_before_it_but_not_the_ones_after_it() -> None:
    document = two_voices()
    # at 0 stand a grace note before (natural) and one after (sharp): a note gets the first
    assert infer(document, Fraction(0), cell=SignCell.NOTE) is _NATURAL
    # a further grace note reads what stands up to its own cell
    assert infer(document, Fraction(0), cell=SignCell.BEFORE) is _NATURAL
    assert infer(document, Fraction(0), cell=SignCell.AFTER) is _SHARP


def test_what_follows_an_anchor_reads_the_grace_notes_after_it() -> None:
    document = two_voices()
    # between 0 and 1/4 the grace note after A (sharp) is the last sign written
    assert infer(document, Fraction(3, 16)) is _SHARP
    # between 1/2 and 5/8 it is the one after D (natural), not the notes of 1/2 (sharp)
    assert infer(document, Fraction(9, 16)) is _NATURAL
    # at 5/8 a note reads the grace note before I (flat); later ones read I
    assert infer(document, Fraction(5, 8)) is _FLAT
    assert infer(document, Fraction(3, 4)) is _FLAT


def test_a_grace_sign_does_not_cross_the_barline() -> None:
    document = two_voices()
    assert infer(document, Fraction(7, 8)) is _FLAT
    assert infer(document, Fraction(1)) is _NATURAL


def test_the_index_follows_a_grace_note_it_is_told_of() -> None:
    document = ScoreDocument.create_fresh(staff_count=2, voice_count=2, measure_count=2)
    geometry = ScoreGeometry(document=document)
    pitch = ScorePitch(
        document=document,
        geometry=geometry,
        contexts=ContextIndex(document=document, geometry=geometry),
    )
    point = Point(frame=geometry.root, value=Fraction(1, 4))
    assert (
        pitch.accidental_at(
            staff=document.staffs[0], point=point, staff_step=-2, cell=SignCell.NOTE
        )
        is _NATURAL
    )

    host = note(document, Fraction(0), _NATURAL)
    pitch.invalidate_note(note=host)
    sign = grace(document, host, GracePlacement.AFTER, _SHARP)
    pitch.invalidate_note(note=sign)
    assert (
        pitch.accidental_at(
            staff=document.staffs[0], point=point, staff_step=-2, cell=SignCell.NOTE
        )
        is _SHARP
    )
