from fractions import Fraction

from tests.unit.domain.document_builders import anchor

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import (
    ClefChange,
    Context,
    KeySignatureChange,
    OctaveTransposition,
)
from piano_app.domain.score.document.models.notation import Accidental, Clef
from piano_app.domain.score.document.services.contexts import ContextIndex, Scope
from piano_app.domain.score.document.services.geometry import Piece, Point
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.pitch.modifiers import (
    MODIFIERS,
    Composition,
    in_force,
)
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch

_ONE: Fraction = Fraction(1)
_TWO: Fraction = Fraction(2)
_THREE: Fraction = Fraction(3)


def _document() -> ScoreDocument:
    return ScoreDocument.create_fresh(voice_count=1, staff_count=1, measure_count=3)


def test_the_modifiers_of_pitch_and_how_each_composes() -> None:
    modifiers: dict[type[Context], Composition] = dict(MODIFIERS)

    assert modifiers == {
        ClefChange: Composition.EXCLUSIVE,
        KeySignatureChange: Composition.EXCLUSIVE,
        OctaveTransposition: Composition.ADDITIVE,
    }


def test_an_exclusive_kind_counts_the_one_that_governs_and_an_additive_one_all_it_covers() -> None:
    document: ScoreDocument = _document()
    staff = document.staffs[0]
    bass: ClefChange = ClefChange.create(start=anchor(document, _ONE), staff=staff, clef=Clef.BASS)
    outer: OctaveTransposition = OctaveTransposition.create(
        start=anchor(document, _ONE),
        end=anchor(document, _THREE - Fraction(1, 2)),
        staff=staff,
        octaves=1,
    )
    inner: OctaveTransposition = OctaveTransposition.create(
        start=anchor(document, Fraction(3, 2)), end=anchor(document, _TWO), staff=staff, octaves=1
    )
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
    scope: Scope = Scope.of_staff(staff=staff)

    clef_piece: Piece[ClefChange | None, ClefChange] = contexts.piece_at(
        kind=ClefChange, point=Fraction(3, 2), scope=scope
    )
    octave_piece: Piece[OctaveTransposition | None, OctaveTransposition] = contexts.piece_at(
        kind=OctaveTransposition, point=Fraction(7, 4), scope=scope
    )

    assert in_force(kind=ClefChange, piece=clef_piece) == (bass,)
    assert set(in_force(kind=OctaveTransposition, piece=octave_piece)) == {outer, inner}


def test_octave_lines_that_overlap_add_up_in_what_a_step_sounds_like() -> None:
    document: ScoreDocument = _document()
    staff = document.staffs[0]
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
    pitch: ScorePitch = ScorePitch(document=document, geometry=geometry, contexts=contexts)
    at: Point = Point(frame=geometry.root, value=Fraction(7, 4))
    plain: int = pitch.resolve(
        staff=staff, point=at, staff_step=0, accidental=Accidental.NATURAL
    ).midi_note

    OctaveTransposition.create(
        start=anchor(document, _ONE), end=anchor(document, Fraction(5, 2)), staff=staff, octaves=1
    )
    OctaveTransposition.create(
        start=anchor(document, Fraction(3, 2)), end=anchor(document, _TWO), staff=staff, octaves=1
    )
    contexts.invalidate_measures()
    pitch.invalidate_measures()

    assert (
        pitch.resolve(staff=staff, point=at, staff_step=0, accidental=Accidental.NATURAL).midi_note
        == plain + 24
    )
