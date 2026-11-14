from fractions import Fraction

import pytest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import DynamicChange, Hairpin, Refrain
from piano_app.domain.score.document.models.notation import DynamicMarking
from piano_app.domain.score.document.models.structural import Voice
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.playback import Dynamics, build_dynamics, build_route

from ..document_builders import anchor

# Dynamic levels run from 0 (ppp) to 7 (fff): p is 2, mf is 4, f is 5. A measure of the scene is
# one whole note; a new score has p in every voice at its start.

_ONE: Fraction = Fraction(1)
_HALF: Fraction = Fraction(1, 2)


def _document() -> ScoreDocument:
    return ScoreDocument.create_fresh(voice_count=2, staff_count=1, measure_count=4)


def _dynamics(*, document: ScoreDocument) -> Dynamics:
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
    return build_dynamics(
        document=document,
        route=build_route(geometry=geometry, contexts=contexts),
        geometry=geometry,
        contexts=contexts,
    )


def _set(*, document: ScoreDocument, at: Fraction, dynamic: DynamicMarking, voice: int = 0) -> None:
    DynamicChange.create(
        start=anchor(document, at),
        voices=[document.voices[voice]],
        dynamic=dynamic,
    )


def _repeat(*, document: ScoreDocument, first: int, last: int) -> None:
    Refrain.create(
        start=anchor(document, Fraction(first)),
        end=anchor(document, Fraction(last)),
        times=2,
    )


@pytest.mark.unit
def test_a_new_score_is_piano_everywhere() -> None:
    document: ScoreDocument = _document()
    dynamics: Dynamics = _dynamics(document=document)

    assert (
        dynamics.level_at(voice=document.voices[0], position=Fraction(0))
        == DynamicMarking.PIANO.level
    )
    assert dynamics.level_at(voice=document.voices[1], position=_ONE) == DynamicMarking.PIANO.level


@pytest.mark.unit
def test_a_dynamic_holds_from_its_place_until_the_next_one() -> None:
    document: ScoreDocument = _document()
    _set(document=document, at=_ONE, dynamic=DynamicMarking.FORTE)
    voice: Voice = document.voices[0]

    dynamics: Dynamics = _dynamics(document=document)

    assert dynamics.level_at(voice=voice, position=Fraction(3, 4)) == 2
    assert dynamics.level_at(voice=voice, position=_ONE) == 5
    assert dynamics.level_at(voice=voice, position=3 * _ONE) == 5


@pytest.mark.unit
def test_each_voice_has_its_own_dynamic() -> None:
    document: ScoreDocument = _document()
    _set(document=document, at=Fraction(0), dynamic=DynamicMarking.FORTE, voice=1)

    dynamics: Dynamics = _dynamics(document=document)

    assert dynamics.level_at(voice=document.voices[0], position=_HALF) == 2
    assert dynamics.level_at(voice=document.voices[1], position=_HALF) == 5


@pytest.mark.unit
def test_a_hairpin_goes_from_the_level_it_starts_at_by_its_steps_and_the_end_stays() -> None:
    document: ScoreDocument = _document()
    Hairpin.create(
        start=anchor(document, _ONE),
        end=anchor(document, 2 * _ONE),
        voices=[document.voices[0]],
        steps=2,
    )
    voice: Voice = document.voices[0]

    dynamics: Dynamics = _dynamics(document=document)

    assert dynamics.level_at(voice=voice, position=_ONE) == 2
    assert dynamics.level_at(voice=voice, position=_ONE + _HALF) == 3
    assert dynamics.level_at(voice=voice, position=2 * _ONE) == 4
    assert dynamics.level_at(voice=voice, position=3 * _ONE) == 4


@pytest.mark.unit
def test_a_hairpin_is_held_to_the_scale() -> None:
    document: ScoreDocument = _document()
    Hairpin.create(
        start=anchor(document, _ONE),
        end=anchor(document, 2 * _ONE),
        voices=[document.voices[0]],
        steps=-9,
    )

    assert _dynamics(document=document).level_at(voice=document.voices[0], position=3 * _ONE) == 0


@pytest.mark.unit
def test_a_repeat_carries_the_dynamic_over_the_jump() -> None:
    """Measure two is repeated and ends louder than it began (a forte in its middle); the
    second pass begins at that level, it is not restored."""
    document: ScoreDocument = _document()
    _set(document=document, at=Fraction(3, 2), dynamic=DynamicMarking.FORTE)
    _repeat(document=document, first=1, last=2)
    voice: Voice = document.voices[0]

    dynamics: Dynamics = _dynamics(document=document)

    # played: measure one, measure two, then measure two again, then measures three and four
    assert dynamics.level_at(voice=voice, position=2 * _ONE + Fraction(1, 4)) == 5
    assert dynamics.level_at(voice=voice, position=_ONE + Fraction(1, 4)) == 2


@pytest.mark.unit
def test_a_hairpin_cut_by_a_jump_keeps_the_level_it_reached() -> None:
    """The crescendo begins in the middle of measure two and ends in measure three; measure two
    is repeated, so the first pass is cut halfway: the second begins at the level reached."""
    document: ScoreDocument = _document()
    Hairpin.create(
        start=anchor(document, Fraction(3, 2)),
        end=anchor(document, Fraction(5, 2)),
        voices=[document.voices[0]],
        steps=2,
    )
    _repeat(document=document, first=1, last=2)

    dynamics: Dynamics = _dynamics(document=document)

    assert dynamics.level_at(voice=document.voices[0], position=2 * _ONE + Fraction(1, 4)) == 3


@pytest.mark.unit
def test_a_position_outside_the_score_is_refused() -> None:
    document: ScoreDocument = _document()

    with pytest.raises(ValueError, match="outside"):
        _dynamics(document=document).level_at(voice=document.voices[0], position=5 * _ONE)
