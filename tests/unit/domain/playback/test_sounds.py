from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.context import Refrain
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import RhythmicValue
from piano_app.domain.score.document.models.relations import Tie
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.playback import Sound, build_route, build_sounds

from ..scene import Score, anchor_at, build_score, insert_note, note, note_at, quarters

# A measure of the scene is four quarters, one whole note long: quarter k of measure m starts
# at m + k / 4. The sounds are read as (start, end, how many notes are tied in it) in the time
# of the route.

_Q: Fraction = Fraction(1, 4)

type Shape = tuple[Fraction, Fraction, int]


def _sounds(*, score: Score) -> list[Sound]:
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)
    route = build_route(
        geometry=geometry,
        contexts=ContextIndex(document=score.document, geometry=geometry),
    )

    return build_sounds(document=score.document, geometry=geometry, route=route)


def _shapes(*, score: Score) -> list[Shape]:
    return [(sound.start, sound.end, len(sound.notes)) for sound in _sounds(score=score)]


def _repeat(*, score: Score, first: Fraction, last: Fraction | None) -> None:
    Refrain.create(
        start=anchor_at(score=score, at=first),
        end=None if last is None else anchor_at(score=score, at=last),
        times=2,
    )


@pytest.mark.unit
def test_a_note_is_a_sound_from_its_start_to_its_end() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(1,))

    assert _shapes(score=score) == [(_Q, 2 * _Q, 1)]


@pytest.mark.unit
def test_a_rest_makes_no_sound() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0, 2))

    assert _shapes(score=score) == [(Fraction(0), _Q, 1), (2 * _Q, 3 * _Q, 1)]


@pytest.mark.unit
def test_tied_notes_are_one_sound_from_the_first_start_to_the_last_end() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0, 1, 2))
    first: Note = note_at(score=score, at=Fraction(0))
    second: Note = note_at(score=score, at=_Q)
    third: Note = note_at(score=score, at=2 * _Q)
    Tie.create(start_note=first, end_note=second)
    Tie.create(start_note=second, end_note=third)

    (sound,) = _sounds(score=score)

    assert sound.notes == (first, second, third)
    assert (sound.start, sound.end) == (Fraction(0), 3 * _Q)


@pytest.mark.unit
def test_a_chord_with_one_note_tied_gives_a_long_sound_and_two_short_ones() -> None:
    """Chords on beats one and two; only their lower notes are tied."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0, 1))
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)
    insert_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER)
    lower: Note = note_at(score=score, at=Fraction(0))
    Tie.create(start_note=lower, end_note=note_at(score=score, at=_Q))

    assert _shapes(score=score) == [
        (Fraction(0), 2 * _Q, 2),
        (Fraction(0), _Q, 1),
        (_Q, 2 * _Q, 1),
    ]


@pytest.mark.unit
def test_a_repeated_note_sounds_once_in_each_pass() -> None:
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    _repeat(score=score, first=Fraction(0), last=Fraction(1))

    sounds: list[Sound] = _sounds(score=score)

    assert [sound.start for sound in sounds] == [
        *(Fraction(beat, 4) for beat in range(4)),
        *(1 + Fraction(beat, 4) for beat in range(4)),
    ]
    assert sounds[0].notes == sounds[4].notes


@pytest.mark.unit
def test_a_tie_across_a_repeat_holds_only_in_the_pass_that_goes_on() -> None:
    """The last note of measure one is tied to the first note of measure two; measure one is
    repeated. The first pass goes back to measure one, so the tie is cut; the second goes on
    to measure two, so the two notes are one sound."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(3,))
    quarters(score=score, measure=1, beats=(0,))
    Tie.create(
        start_note=note_at(score=score, at=3 * _Q),
        end_note=note_at(score=score, at=Fraction(1)),
    )
    _repeat(score=score, first=Fraction(0), last=Fraction(1))

    assert _shapes(score=score) == [
        (3 * _Q, Fraction(1), 1),
        (1 + 3 * _Q, 1 + Fraction(5, 4), 2),
    ]


@pytest.mark.unit
def test_the_end_of_a_tie_sounds_again_when_the_pass_jumps_in_at_it() -> None:
    """Measure two is repeated and is tied to from measure one. The first pass comes from
    measure one, the second jumps back to measure two, whose first note then sounds by itself."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(3,))
    quarters(score=score, measure=1, beats=(0,))
    Tie.create(
        start_note=note_at(score=score, at=3 * _Q),
        end_note=note_at(score=score, at=Fraction(1)),
    )
    _repeat(score=score, first=Fraction(1), last=None)

    assert _shapes(score=score) == [
        (3 * _Q, Fraction(1) + _Q, 2),
        (Fraction(2), Fraction(2) + _Q, 1),
    ]


@pytest.mark.unit
def test_a_note_the_first_pass_ends_inside_is_cut_there_and_played_whole_in_the_second() -> None:
    """A half note, and a repeat over the first quarter of it: the first pass plays that
    quarter and goes back; the second goes on and plays the note to its end."""
    score: Score = build_score(measure_count=2)
    note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.HALF,
        step=0,
    )
    _repeat(score=score, first=Fraction(0), last=_Q)

    assert _shapes(score=score) == [(Fraction(0), _Q, 1), (_Q, 3 * _Q, 1)]
