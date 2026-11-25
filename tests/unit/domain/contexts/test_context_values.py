from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.context import (
    DynamicChange,
    Hairpin,
    TempoChange,
    TempoTransition,
)
from piano_app.domain.score.document.models.notation import (
    DottedRhythmicValue,
    DynamicMarking,
    RhythmicValue,
)
from piano_app.domain.score.document.services.contexts import ContextIndex, ContextValues, Tempo
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry

from ..scene import Score, anchor_at, build_score, build_two_voices

# The tempo and the dynamic in force at a place: a point sets the value from its position on,
# a gradual change starts from the value in force at its start and ends at a value derived
# from it, which stays until the next point.

_QUARTER: DottedRhythmicValue = DottedRhythmicValue(value=RhythmicValue.QUARTER)
_DOTTED_EIGHTH: DottedRhythmicValue = DottedRhythmicValue(value=RhythmicValue.EIGHTH, dots_count=1)


def _values(score: Score) -> ContextValues:
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)

    return ContextValues(
        contexts=ContextIndex(document=score.document, geometry=geometry), geometry=geometry
    )


def _tempo(score: Score, at: Fraction, bpm: int, beat: DottedRhythmicValue = _QUARTER) -> None:
    TempoChange.create(start=anchor_at(score=score, at=at), beat=beat, bpm=bpm)


def _transition(score: Score, start: Fraction, end: Fraction, ratio: Fraction) -> TempoTransition:
    return TempoTransition.create(
        start=anchor_at(score=score, at=start), end=anchor_at(score=score, at=end), ratio=ratio
    )


def _dynamic(score: Score, at: Fraction, dynamic: DynamicMarking) -> None:
    DynamicChange.create(start=anchor_at(score=score, at=at), voice=score.voice, dynamic=dynamic)


def _hairpin(score: Score, start: Fraction, end: Fraction, steps: int) -> Hairpin:
    return Hairpin.create(
        start=anchor_at(score=score, at=start),
        end=anchor_at(score=score, at=end),
        voice=score.voice,
        steps=steps,
    )


# --- tempo ------------------------------------------------------------------------------


@pytest.mark.unit
def test_the_score_starts_at_ninety_quarters_a_minute() -> None:
    score: Score = build_score(measure_count=2)

    assert _values(score).tempo_at(at=Fraction(0)) == Tempo(beat=_QUARTER, bpm=Fraction(90))
    assert _values(score).tempo_at(at=Fraction(7, 4)) == Tempo(beat=_QUARTER, bpm=Fraction(90))


@pytest.mark.unit
def test_a_tempo_change_sets_the_tempo_from_its_position_on() -> None:
    score: Score = build_score(measure_count=3)
    _tempo(score, Fraction(1), 120, _DOTTED_EIGHTH)

    values: ContextValues = _values(score)

    assert values.tempo_at(at=Fraction(3, 4)).bpm == 90
    assert values.tempo_at(at=Fraction(1)) == Tempo(beat=_DOTTED_EIGHTH, bpm=Fraction(120))
    assert values.tempo_at(at=Fraction(5, 2)).bpm == 120


@pytest.mark.unit
def test_a_transition_ends_at_its_ratio_of_the_tempo_it_starts_from() -> None:
    score: Score = build_score(measure_count=3)
    ritardando: TempoTransition = _transition(score, Fraction(1), Fraction(2), Fraction(7, 9))

    values: ContextValues = _values(score)

    assert values.transition_start_tempo(transition=ritardando).bpm == 90
    assert values.transition_end_tempo(transition=ritardando).bpm == 70
    assert values.transition_end_tempo(transition=ritardando).beat == _QUARTER


@pytest.mark.unit
def test_inside_a_transition_the_tempo_is_the_one_it_starts_from_and_after_it_the_end_one() -> None:
    score: Score = build_score(measure_count=4)
    _transition(score, Fraction(1), Fraction(2), Fraction(7, 9))

    values: ContextValues = _values(score)

    assert values.tempo_at(at=Fraction(1, 2)).bpm == 90
    assert values.tempo_at(at=Fraction(1)).bpm == 90
    assert values.tempo_at(at=Fraction(3, 2)).bpm == 90
    assert values.tempo_at(at=Fraction(2)).bpm == 70
    assert values.tempo_at(at=Fraction(7, 2)).bpm == 70


@pytest.mark.unit
def test_a_tempo_change_at_the_start_of_a_transition_is_what_it_starts_from() -> None:
    score: Score = build_score(measure_count=3)
    _tempo(score, Fraction(1), 60)
    transition: TempoTransition = _transition(score, Fraction(1), Fraction(2), Fraction(1, 2))

    values: ContextValues = _values(score)

    assert values.transition_start_tempo(transition=transition).bpm == 60
    assert values.transition_end_tempo(transition=transition).bpm == 30


@pytest.mark.unit
def test_a_tempo_change_at_the_end_of_a_transition_takes_over_after_it_ends() -> None:
    score: Score = build_score(measure_count=3)
    transition: TempoTransition = _transition(score, Fraction(1), Fraction(2), Fraction(7, 9))
    _tempo(score, Fraction(2), 100)

    values: ContextValues = _values(score)

    assert values.transition_end_tempo(transition=transition).bpm == 70
    assert values.tempo_at(at=Fraction(2)).bpm == 100


@pytest.mark.unit
def test_a_transition_starting_where_another_ended_starts_from_its_end_tempo() -> None:
    score: Score = build_score(measure_count=5)
    first: TempoTransition = _transition(score, Fraction(1), Fraction(2), Fraction(7, 9))
    second: TempoTransition = _transition(score, Fraction(3), Fraction(4), Fraction(6, 5))

    values: ContextValues = _values(score)

    assert values.transition_end_tempo(transition=first).bpm == 70
    assert values.transition_start_tempo(transition=second).bpm == 70
    assert values.transition_end_tempo(transition=second).bpm == 84


@pytest.mark.unit
def test_editing_the_base_tempo_moves_every_transition_after_it() -> None:
    """The cascade: 90 → 70 → 84 becomes 60 → 46⅔ → 56 once the first tempo is 60."""
    score: Score = build_score(measure_count=5)
    first: TempoTransition = _transition(score, Fraction(1), Fraction(2), Fraction(7, 9))
    second: TempoTransition = _transition(score, Fraction(3), Fraction(4), Fraction(6, 5))
    _tempo(score, Fraction(1, 2), 60)

    values: ContextValues = _values(score)

    assert values.transition_start_tempo(transition=first).bpm == 60
    assert values.transition_end_tempo(transition=first).bpm == Fraction(140, 3)
    assert values.transition_end_tempo(transition=second).bpm == Fraction(140, 3) * Fraction(6, 5)


@pytest.mark.unit
def test_a_transition_keeps_the_beat_of_the_tempo_it_starts_from() -> None:
    score: Score = build_score(measure_count=3)
    _tempo(score, Fraction(1, 2), 100, _DOTTED_EIGHTH)
    transition: TempoTransition = _transition(score, Fraction(1), Fraction(2), Fraction(3, 2))

    assert _values(score).transition_end_tempo(transition=transition) == Tempo(
        beat=_DOTTED_EIGHTH, bpm=Fraction(150)
    )


@pytest.mark.unit
def test_a_transition_that_is_not_in_the_score_has_no_tempo() -> None:
    score: Score = build_score(measure_count=3)
    elsewhere: Score = build_score(measure_count=3)
    stranger: TempoTransition = _transition(elsewhere, Fraction(1), Fraction(2), Fraction(1, 2))

    with pytest.raises(ValueError, match="not in the score"):
        _values(score).transition_start_tempo(transition=stranger)

    with pytest.raises(ValueError, match="not in the score"):
        _values(score).transition_end_tempo(transition=stranger)


# --- dynamics ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_voice_starts_at_piano_and_a_dynamic_sets_it_from_its_position_on() -> None:
    score: Score = build_score(measure_count=3)
    _dynamic(score, Fraction(1), DynamicMarking.FORTE)

    values: ContextValues = _values(score)

    assert values.dynamic_at(voice=score.voice, at=Fraction(0)) is DynamicMarking.PIANO
    assert values.dynamic_at(voice=score.voice, at=Fraction(1)) is DynamicMarking.FORTE
    assert values.dynamic_at(voice=score.voice, at=Fraction(5, 2)) is DynamicMarking.FORTE


@pytest.mark.unit
def test_a_hairpin_ends_the_given_number_of_levels_from_where_it_starts() -> None:
    score: Score = build_score(measure_count=3)
    crescendo: Hairpin = _hairpin(score, Fraction(1), Fraction(2), 3)
    values: ContextValues = _values(score)

    assert values.hairpin_start_dynamic(hairpin=crescendo, voice=score.voice) is (
        DynamicMarking.PIANO
    )
    assert values.hairpin_end_dynamic(hairpin=crescendo, voice=score.voice) is (
        DynamicMarking.FORTE
    )
    assert values.dynamic_at(voice=score.voice, at=Fraction(3, 2)) is DynamicMarking.PIANO
    assert values.dynamic_at(voice=score.voice, at=Fraction(2)) is DynamicMarking.FORTE


@pytest.mark.unit
def test_a_diminuendo_goes_down_and_is_held_to_the_scale() -> None:
    score: Score = build_score(measure_count=3)
    diminuendo: Hairpin = _hairpin(score, Fraction(1), Fraction(2), -5)

    assert (
        _values(score).hairpin_end_dynamic(hairpin=diminuendo, voice=score.voice)
        is DynamicMarking.PIANISSIMISSIMO
    )


@pytest.mark.unit
def test_editing_the_dynamic_before_a_hairpin_moves_where_it_ends() -> None:
    score: Score = build_score(measure_count=3)
    crescendo: Hairpin = _hairpin(score, Fraction(1), Fraction(2), 3)
    _dynamic(score, Fraction(1, 2), DynamicMarking.FORTISSIMO)

    values: ContextValues = _values(score)

    assert values.hairpin_start_dynamic(hairpin=crescendo, voice=score.voice) is (
        DynamicMarking.FORTISSIMO
    )
    assert values.hairpin_end_dynamic(hairpin=crescendo, voice=score.voice) is (
        DynamicMarking.FORTISSIMISSIMO
    )


@pytest.mark.unit
def test_the_dynamic_after_a_hairpin_is_its_end_until_the_next_dynamic() -> None:
    score: Score = build_score(measure_count=4)
    _hairpin(score, Fraction(1), Fraction(2), 2)
    _dynamic(score, Fraction(3), DynamicMarking.PIANISSIMO)

    values: ContextValues = _values(score)

    assert values.dynamic_at(voice=score.voice, at=Fraction(5, 2)) is DynamicMarking.MEZZO_FORTE
    assert values.dynamic_at(voice=score.voice, at=Fraction(3)) is DynamicMarking.PIANISSIMO


@pytest.mark.unit
def test_each_voice_has_its_own_dynamic() -> None:
    first, second = build_two_voices(measure_count=3)
    for voice in (first.voice, second.voice):
        DynamicChange.create(
            start=anchor_at(score=first, at=Fraction(1)),
            voice=voice,
            dynamic=DynamicMarking.FORTE,
        )
    DynamicChange.create(
        start=anchor_at(score=first, at=Fraction(2)),
        voice=first.voice,
        dynamic=DynamicMarking.MEZZO_PIANO,
    )

    values: ContextValues = _values(first)

    assert values.dynamic_at(voice=first.voice, at=Fraction(5, 2)) is DynamicMarking.MEZZO_PIANO
    assert values.dynamic_at(voice=second.voice, at=Fraction(5, 2)) is DynamicMarking.FORTE


@pytest.mark.unit
def test_a_hairpin_of_other_voices_does_not_move_this_voice() -> None:
    first, second = build_two_voices(measure_count=3)
    hairpin: Hairpin = Hairpin.create(
        start=anchor_at(score=first, at=Fraction(1)),
        end=anchor_at(score=first, at=Fraction(2)),
        voice=second.voice,
        steps=3,
    )

    values: ContextValues = _values(first)

    assert values.dynamic_at(voice=first.voice, at=Fraction(5, 2)) is DynamicMarking.PIANO
    assert values.dynamic_at(voice=second.voice, at=Fraction(5, 2)) is DynamicMarking.FORTE
    with pytest.raises(ValueError, match="does not name this voice"):
        values.hairpin_end_dynamic(hairpin=hairpin, voice=first.voice)

    with pytest.raises(ValueError, match="does not name this voice"):
        values.hairpin_start_dynamic(hairpin=hairpin, voice=first.voice)


@pytest.mark.unit
def test_a_score_without_its_start_contexts_has_no_tempo_and_no_dynamic() -> None:
    score: Score = build_score(measure_count=2, start_contexts=False)

    with pytest.raises(ValueError, match="No tempo is in force"):
        _values(score).tempo_at(at=Fraction(0))

    with pytest.raises(ValueError, match="No dynamic is in force"):
        _values(score).dynamic_at(voice=score.voice, at=Fraction(0))
