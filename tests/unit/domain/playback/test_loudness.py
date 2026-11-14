from fractions import Fraction

import pytest

from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.models.context import DynamicChange, Hairpin
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import (
    Accidental,
    Articulation,
    DynamicMarking,
    GracePlacement,
)
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch
from piano_app.domain.score.document.services.playback import (
    DynamicCurve,
    build_dynamics,
    build_route,
    build_sounds,
    expand_sounds,
    velocities,
)

from ..document_builders import anchor
from ..pitch.test_accidental_inference import note
from ..pitch.test_grace_signs import grace

# The piano profile: dynamic levels 0 (ppp) to 7 (fff) give velocities 16, 19, 31, 56, 86, 111,
# 123, 126. A new score is piano (level 2) in every voice.

_CURVE: DynamicCurve = DynamicCurve()
_NATURAL = Accidental.NATURAL


def _document() -> ScoreDocument:
    return ScoreDocument.create_fresh(voice_count=2, staff_count=1, measure_count=2)


def _velocities(*, document: ScoreDocument) -> list[int]:
    """The velocity of every note of the score, in the order the notes start."""
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
    route = build_route(geometry=geometry, contexts=contexts)
    played = expand_sounds(
        sounds=build_sounds(document=document, geometry=geometry, route=route),
        document=document,
        geometry=geometry,
        pitch=ScorePitch(document=document, geometry=geometry, contexts=contexts),
    )

    return velocities(
        notes=played,
        dynamics=build_dynamics(
            document=document, route=route, geometry=geometry, contexts=contexts
        ),
        curve=_CURVE,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("level", "velocity"),
    [(0, 16), (1, 19), (2, 31), (3, 56), (4, 86), (5, 111), (6, 123), (7, 126)],
)
def test_the_curve_gives_the_velocity_of_each_level(level: int, velocity: int) -> None:
    assert _CURVE.velocity_at(level=level) == velocity


@pytest.mark.unit
def test_the_curve_is_held_to_its_ends_and_rises_between_levels() -> None:
    assert _CURVE.velocity_at(level=-3) == 16
    assert _CURVE.velocity_at(level=11) == 126
    assert 31 < _CURVE.velocity_at(level=2.5) < 56


@pytest.mark.unit
def test_a_curve_with_nonsense_parameters_is_refused() -> None:
    with pytest.raises(ValueError, match="increasing"):
        DynamicCurve(min_level=3, max_level=3)

    with pytest.raises(ValueError, match="velocities"):
        DynamicCurve(min_velocity=0)


@pytest.mark.unit
def test_a_note_is_struck_at_the_dynamic_of_its_voice() -> None:
    document: ScoreDocument = _document()
    note(document, Fraction(0), _NATURAL)
    note(document, Fraction(1, 4), _NATURAL, voice=1)
    DynamicChange.create(
        start=anchor(document, Fraction(0)),
        voices=[document.voices[1]],
        dynamic=DynamicMarking.MEZZO_FORTE,
    )

    assert _velocities(document=document) == [31, 86]


@pytest.mark.unit
def test_an_accent_and_a_marcato_make_a_note_louder_by_levels() -> None:
    document: ScoreDocument = _document()
    accented: Note = note(document, Fraction(0), _NATURAL)
    marked: Note = note(document, Fraction(1, 4), _NATURAL)
    accented.note_carrier.set_articulations(articulations=frozenset({Articulation.ACCENT}))
    marked.note_carrier.set_articulations(articulations=frozenset({Articulation.MARCATO}))

    assert _velocities(document=document) == [56, 86]


@pytest.mark.unit
def test_a_note_in_a_crescendo_is_struck_at_the_level_where_it_starts() -> None:
    document: ScoreDocument = _document()
    note(document, Fraction(0), _NATURAL)
    note(document, Fraction(1, 2), _NATURAL)
    note(document, Fraction(1), _NATURAL)
    Hairpin.create(
        start=anchor(document, Fraction(0)),
        end=anchor(document, Fraction(1)),
        voices=[document.voices[0]],
        steps=2,
    )

    assert _velocities(document=document) == [31, 56, 86]


@pytest.mark.unit
def test_a_grace_note_is_struck_at_the_dynamic_of_the_voice_of_its_note() -> None:
    document: ScoreDocument = _document()
    host: Note = note(document, Fraction(0), _NATURAL, voice=1)
    grace(document, host, GracePlacement.BEFORE, _NATURAL)
    DynamicChange.create(
        start=anchor(document, Fraction(0)),
        voices=[document.voices[1]],
        dynamic=DynamicMarking.FORTE,
    )

    assert _velocities(document=document) == [111, 111]
