from fractions import Fraction
from math import log

import pytest

from piano_app.domain.score.document.models.context import Refrain, TempoChange, TempoTransition
from piano_app.domain.score.document.models.notation import DottedRhythmicValue, RhythmicValue
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.playback import Timeline, build_route, build_timeline

from ..scene import Score, anchor_at, build_score

# A measure of the scene is one whole note. At a quarter = 120 a whole note takes 2000 ms.

_ONE: Fraction = Fraction(1)
_HALF: Fraction = Fraction(1, 2)


def _score(*, measures: int) -> Score:
    return build_score(measure_count=measures, start_contexts=False)


def _tempo(
    *,
    score: Score,
    at: Fraction,
    bpm: int,
    beat: RhythmicValue = RhythmicValue.QUARTER,
) -> None:
    TempoChange.create(
        start=anchor_at(score=score, at=at),
        beat=DottedRhythmicValue(value=beat),
        bpm=bpm,
    )


def _timeline(*, score: Score) -> Timeline:
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)
    contexts: ContextIndex = ContextIndex(document=score.document, geometry=geometry)
    return build_timeline(
        route=build_route(geometry=geometry, contexts=contexts),
        geometry=geometry,
        contexts=contexts,
    )


def _repeat(*, score: Score, first: Fraction, last: Fraction | None) -> None:
    Refrain.create(
        start=anchor_at(score=score, at=first),
        end=None if last is None else anchor_at(score=score, at=last),
        times=2,
    )


@pytest.mark.unit
def test_a_constant_tempo_gives_a_time_in_proportion_to_the_position() -> None:
    score: Score = _score(measures=2)
    _tempo(score=score, at=Fraction(0), bpm=120)

    timeline: Timeline = _timeline(score=score)

    assert timeline.ms_at(position=Fraction(0)) == 0
    assert timeline.ms_at(position=Fraction(1, 4)) == pytest.approx(500)
    assert timeline.ms_at(position=_ONE) == pytest.approx(2000)
    assert timeline.ms_at(position=2 * _ONE) == pytest.approx(4000)


@pytest.mark.unit
def test_the_beat_unit_of_a_tempo_is_taken_into_account() -> None:
    """An eighth = 240 is the same speed as a quarter = 120."""
    score: Score = _score(measures=1)
    _tempo(score=score, at=Fraction(0), bpm=240, beat=RhythmicValue.EIGHTH)

    assert _timeline(score=score).ms_at(position=_ONE) == pytest.approx(2000)


@pytest.mark.unit
def test_a_new_tempo_changes_the_speed_from_its_place_on() -> None:
    score: Score = _score(measures=2)
    _tempo(score=score, at=Fraction(0), bpm=120)
    _tempo(score=score, at=_ONE, bpm=60)

    timeline: Timeline = _timeline(score=score)

    assert timeline.ms_at(position=_ONE) == pytest.approx(2000)
    assert timeline.ms_at(position=2 * _ONE) == pytest.approx(6000)


@pytest.mark.unit
def test_a_transition_goes_from_one_speed_to_another_and_the_new_speed_stays() -> None:
    """A ritardando over a measure to half the speed: the time over it is the integral of the
    reciprocal of a speed that goes linearly from 30 to 15 whole notes a minute."""
    score: Score = _score(measures=2)
    _tempo(score=score, at=Fraction(0), bpm=120)
    TempoTransition.create(
        start=anchor_at(score=score, at=Fraction(0)),
        end=anchor_at(score=score, at=_ONE),
        ratio=_HALF,
    )

    timeline: Timeline = _timeline(score=score)

    over: float = 60000 * log(2) / 15
    assert timeline.ms_at(position=_ONE) == pytest.approx(over)
    assert timeline.ms_at(position=2 * _ONE) == pytest.approx(over + 4000)


@pytest.mark.unit
def test_a_repeat_carries_the_tempo_over_the_jump() -> None:
    """Measure two slows down in its second half and is repeated: the second pass begins at
    the slower tempo, it is not restored."""
    score: Score = _score(measures=3)
    _tempo(score=score, at=Fraction(0), bpm=120)
    _tempo(score=score, at=Fraction(3, 2), bpm=60)
    _repeat(score=score, first=_ONE, last=2 * _ONE)

    timeline: Timeline = _timeline(score=score)

    assert timeline.ms_at(position=2 * _ONE) == pytest.approx(2000 + 1000 + 2000)
    assert timeline.ms_at(position=2 * _ONE + _HALF) == pytest.approx(5000 + 2000)
    assert timeline.ms_at(position=3 * _ONE) == pytest.approx(5000 + 4000)
    assert timeline.ms_at(position=4 * _ONE) == pytest.approx(9000 + 4000)


@pytest.mark.unit
def test_a_tempo_written_at_the_start_of_a_repeated_part_is_read_again_in_each_pass() -> None:
    score: Score = _score(measures=2)
    _tempo(score=score, at=Fraction(0), bpm=120)
    _tempo(score=score, at=_HALF, bpm=60)
    _repeat(score=score, first=Fraction(0), last=_ONE)

    timeline: Timeline = _timeline(score=score)

    assert timeline.ms_at(position=_ONE) == pytest.approx(1000 + 2000)
    assert timeline.ms_at(position=_ONE + _HALF) == pytest.approx(3000 + 1000)


@pytest.mark.unit
def test_a_transition_cut_by_a_jump_keeps_the_speed_it_reached() -> None:
    """The ritardando begins in the middle of measure two and ends in the middle of measure
    three; measure two is repeated. The first pass is cut at the end of the measure, halfway
    through the change, and the second pass begins at the speed reached then."""
    score: Score = _score(measures=4)
    _tempo(score=score, at=Fraction(0), bpm=120)
    TempoTransition.create(
        start=anchor_at(score=score, at=Fraction(3, 2)),
        end=anchor_at(score=score, at=Fraction(5, 2)),
        ratio=_HALF,
    )
    _repeat(score=score, first=_ONE, last=2 * _ONE)

    timeline: Timeline = _timeline(score=score)

    # halfway the speed has gone from 30 to 22.5 whole notes a minute
    assert timeline.ms_at(position=2 * _ONE + _HALF) - timeline.ms_at(
        position=2 * _ONE
    ) == pytest.approx(60000 * 0.5 / 22.5)


@pytest.mark.unit
def test_a_score_without_a_tempo_is_refused() -> None:
    score: Score = _score(measures=1)

    with pytest.raises(ValueError, match="No tempo"):
        _timeline(score=score)


@pytest.mark.unit
def test_a_position_outside_the_score_is_refused() -> None:
    score: Score = _score(measures=1)
    _tempo(score=score, at=Fraction(0), bpm=120)

    with pytest.raises(ValueError, match="outside"):
        _timeline(score=score).ms_at(position=2 * _ONE)
