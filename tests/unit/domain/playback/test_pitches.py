from fractions import Fraction

import pytest

from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import (
    Accidental,
    GlissandoType,
    GracePlacement,
)
from piano_app.domain.score.document.models.relations import Glissando
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch
from piano_app.domain.score.document.services.playback import glissando_pitches, neighbour_pitch

from ..pitch.test_accidental_inference import key, note
from ..pitch.test_grace_signs import grace

# On the treble staff staff step 0 is E4 (MIDI 64), step -2 is C4 (60) and step 5 is C5 (72); on
# the bass staff staff step 0 is G2 (43). Two staffs, two voices, two measures of one whole note.

_NATURAL = Accidental.NATURAL
_SHARP = Accidental.SHARP
# the sign of each diatonic step from C to B: C and F sharp
_D_MAJOR: tuple[Accidental, ...] = (
    _SHARP,
    _NATURAL,
    _NATURAL,
    _SHARP,
    _NATURAL,
    _NATURAL,
    _NATURAL,
)
_Q: Fraction = Fraction(1, 4)


def _document() -> ScoreDocument:
    return ScoreDocument.create_fresh(voice_count=2, staff_count=2, measure_count=2)


def _tools(*, document: ScoreDocument) -> tuple[ScoreGeometry, ScorePitch]:
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    return geometry, ScorePitch(
        document=document,
        geometry=geometry,
        contexts=ContextIndex(document=document, geometry=geometry),
    )


def _neighbour(*, document: ScoreDocument, main: Note, steps: int) -> int:
    geometry, pitch = _tools(document=document)
    return neighbour_pitch(note=main, steps=steps, geometry=geometry, pitch=pitch)


def _glissando(*, document: ScoreDocument, start: Note, end: Note) -> list[int]:
    geometry, pitch = _tools(document=document)
    glissando: Glissando = Glissando.create(
        start_note=start,
        end_note=end,
        glissando_type=GlissandoType.STRAIGHT,
    )
    return glissando_pitches(glissando=glissando, geometry=geometry, pitch=pitch)


@pytest.mark.unit
def test_the_neighbours_of_f_sharp_in_d_major_follow_the_key() -> None:
    document: ScoreDocument = _document()
    key(document, Fraction(0), _D_MAJOR)
    main: Note = note(document, Fraction(0), _SHARP, step=1)

    assert _neighbour(document=document, main=main, steps=1) == 67  # G, no sign in the key
    assert _neighbour(document=document, main=main, steps=-1) == 64  # E
    assert _neighbour(document=document, main=main, steps=2) == 69  # A


@pytest.mark.unit
def test_a_sign_written_earlier_in_the_measure_is_kept() -> None:
    document: ScoreDocument = _document()
    key(document, Fraction(0), _D_MAJOR)
    note(document, Fraction(0), _SHARP, step=2)
    main: Note = note(document, _Q, _SHARP, step=1)

    assert _neighbour(document=document, main=main, steps=1) == 68  # G sharp


@pytest.mark.unit
def test_a_sign_written_in_another_voice_is_kept() -> None:
    document: ScoreDocument = _document()
    note(document, Fraction(0), _SHARP, step=2, voice=1)
    main: Note = note(document, _Q, _NATURAL, step=1)

    assert _neighbour(document=document, main=main, steps=1) == 68


@pytest.mark.unit
def test_a_sign_does_not_reach_the_next_measure() -> None:
    document: ScoreDocument = _document()
    note(document, Fraction(0), _SHARP, step=2)
    main: Note = note(document, Fraction(1), _NATURAL, step=1)

    assert _neighbour(document=document, main=main, steps=1) == 67


@pytest.mark.unit
def test_the_neighbours_on_the_bass_staff_are_counted_on_that_staff() -> None:
    document: ScoreDocument = _document()
    main: Note = note(document, Fraction(0), _NATURAL, step=0, staff=1)

    assert _neighbour(document=document, main=main, steps=1) == 45  # A2
    assert _neighbour(document=document, main=main, steps=-1) == 41  # F2


@pytest.mark.unit
def test_a_grace_note_reads_the_signs_up_to_its_own_place() -> None:
    """The host note is D sharp. A grace note before it does not read the host's sign; one
    after it does."""
    document: ScoreDocument = _document()
    host: Note = note(document, Fraction(0), _SHARP, step=-1)
    before: Note = grace(document, host, GracePlacement.BEFORE, _NATURAL)
    after: Note = grace(document, host, GracePlacement.AFTER, _NATURAL)

    assert _neighbour(document=document, main=before, steps=1) == 62  # D
    assert _neighbour(document=document, main=after, steps=1) == 63  # D sharp


@pytest.mark.unit
def test_a_glissando_up_runs_through_the_steps_below_its_end_note() -> None:
    document: ScoreDocument = _document()
    start: Note = note(document, Fraction(0), _NATURAL, step=-2)
    end: Note = note(document, _Q, _NATURAL, step=5)

    assert _glissando(document=document, start=start, end=end) == [60, 62, 64, 65, 67, 69, 71]


@pytest.mark.unit
def test_a_glissando_down_runs_the_other_way() -> None:
    document: ScoreDocument = _document()
    start: Note = note(document, Fraction(0), _NATURAL, step=5)
    end: Note = note(document, _Q, _NATURAL, step=-2)

    assert _glissando(document=document, start=start, end=end) == [72, 71, 69, 67, 65, 64, 62]


@pytest.mark.unit
def test_a_glissando_follows_the_key_and_the_signs_of_the_measure() -> None:
    document: ScoreDocument = _document()
    key(document, Fraction(0), _D_MAJOR)
    start: Note = note(document, Fraction(0), _SHARP, step=-2)
    end: Note = note(document, _Q, _SHARP, step=5)

    assert _glissando(document=document, start=start, end=end) == [61, 62, 64, 66, 67, 69, 71]


@pytest.mark.unit
def test_a_glissando_reads_a_sign_written_before_it_in_the_measure() -> None:
    document: ScoreDocument = _document()
    note(document, Fraction(0), _SHARP, step=2, voice=1)
    start: Note = note(document, _Q, _NATURAL, step=-2)
    end: Note = note(document, 2 * _Q, _NATURAL, step=5)

    assert _glissando(document=document, start=start, end=end) == [60, 62, 64, 65, 68, 69, 71]


@pytest.mark.unit
def test_a_glissando_to_the_next_step_or_to_the_same_one_is_only_its_start() -> None:
    document: ScoreDocument = _document()
    start: Note = note(document, Fraction(0), _NATURAL, step=-2)
    next_step: Note = note(document, _Q, _NATURAL, step=-1)
    same_step: Note = note(document, 2 * _Q, _NATURAL, step=-2)

    assert _glissando(document=document, start=start, end=next_step) == [60]
    assert _glissando(document=document, start=start, end=same_step) == [60]


@pytest.mark.unit
def test_a_glissando_to_a_note_on_another_staff_is_counted_by_its_sound() -> None:
    """C4 on the treble staff to E4 written on the bass staff (step 12): two steps, C and D."""
    document: ScoreDocument = _document()
    start: Note = note(document, Fraction(0), _NATURAL, step=-2)
    end: Note = note(document, _Q, _NATURAL, step=12, staff=1)

    assert _glissando(document=document, start=start, end=end) == [60, 62]
