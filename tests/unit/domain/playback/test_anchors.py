from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.context import Refrain, TempoChange, TempoTransition
from piano_app.domain.score.document.models.notation import DottedRhythmicValue, RhythmicValue
from piano_app.domain.score.document.models.relations import Tie
from piano_app.domain.score.document.services.playback import (
    PlaybackProjection,
    build_projection,
)

from ..scene import Score, anchor_at, build_score, note_at, quarters, rest

# A measure of the scene is one whole note; at a quarter = 120 it takes 2000 ms and a quarter
# 500 ms.

_Q: Fraction = Fraction(1, 4)


def _score(*, measures: int = 2) -> Score:
    score: Score = build_score(measure_count=measures)
    start = anchor_at(score=score, at=Fraction(0))
    for context in tuple(start.starting_contexts):
        if isinstance(context, TempoChange):
            context.detach()

    TempoChange.create(
        start=start,
        beat=DottedRhythmicValue(value=RhythmicValue.QUARTER),
        bpm=120,
    )

    return score


def _repeat(*, score: Score, first: Fraction, last: Fraction) -> None:
    Refrain.create(
        start=anchor_at(score=score, at=first),
        end=anchor_at(score=score, at=last),
        times=2,
    )


@pytest.mark.unit
def test_every_leaf_is_an_anchor_with_its_time_notes_and_rests_alike() -> None:
    score: Score = _score()
    quarters(score=score, measure=0, beats=(0, 2))
    rest(
        score=score,
        parent=score.voice,
        at=_Q,
        rhythmic_value=RhythmicValue.QUARTER,
    )

    projection: PlaybackProjection = build_projection(document=score.document)

    assert [(a.carrier_id, a.start_ms, a.end_ms) for a in projection.anchors] == [
        (
            note_at(score=score, at=Fraction(0)).note_carrier.id,
            pytest.approx(0),
            pytest.approx(500),
        ),
        (projection.anchors[1].carrier_id, pytest.approx(500), pytest.approx(1000)),
        (note_at(score=score, at=2 * _Q).note_carrier.id, pytest.approx(1000), pytest.approx(1500)),
    ]
    assert projection.anchors[1].carrier_id != projection.anchors[0].carrier_id


@pytest.mark.unit
def test_a_repeated_leaf_is_an_anchor_in_each_pass() -> None:
    score: Score = _score()
    quarters(score=score, measure=0, beats=(0,))
    _repeat(score=score, first=Fraction(0), last=Fraction(1))

    projection: PlaybackProjection = build_projection(document=score.document)

    carrier: str = note_at(score=score, at=Fraction(0)).note_carrier.id
    assert [(a.carrier_id, a.start_ms) for a in projection.anchors] == [
        (carrier, pytest.approx(0)),
        (carrier, pytest.approx(2000)),
    ]


@pytest.mark.unit
def test_tied_leaves_are_anchors_of_their_own() -> None:
    score: Score = _score()
    quarters(score=score, measure=0, beats=(0, 1))
    Tie.create(
        start_note=note_at(score=score, at=Fraction(0)),
        end_note=note_at(score=score, at=_Q),
    )

    projection: PlaybackProjection = build_projection(document=score.document)

    assert [(a.start_ms, a.end_ms) for a in projection.anchors] == [
        (pytest.approx(0), pytest.approx(500)),
        (pytest.approx(500), pytest.approx(1000)),
    ]
    assert len(projection.notes) == 1


@pytest.mark.unit
def test_a_score_without_repeats_is_one_segment_with_moments_at_leaves_and_measures() -> None:
    score: Score = _score()
    quarters(score=score, measure=0, beats=(0, 1))

    (segment,) = build_projection(document=score.document).segments

    assert (segment.start, segment.end) == (Fraction(0), Fraction(2))
    assert (segment.start_ms, segment.end_ms) == (pytest.approx(0), pytest.approx(4000))
    assert [(m.position, m.time_ms) for m in segment.moments] == [
        (Fraction(0), pytest.approx(0)),
        (_Q, pytest.approx(500)),
        (2 * _Q, pytest.approx(1000)),
        (Fraction(1), pytest.approx(2000)),
        (Fraction(2), pytest.approx(4000)),
    ]


@pytest.mark.unit
def test_a_repeat_makes_a_segment_for_each_pass() -> None:
    score: Score = _score()
    quarters(score=score, measure=0, beats=(0,))
    _repeat(score=score, first=Fraction(0), last=Fraction(1))

    first, second = build_projection(document=score.document).segments

    assert (first.start, first.end, first.start_ms, first.end_ms) == (
        Fraction(0),
        Fraction(1),
        pytest.approx(0),
        pytest.approx(2000),
    )
    assert (second.start, second.end, second.start_ms, second.end_ms) == (
        Fraction(0),
        Fraction(2),
        pytest.approx(2000),
        pytest.approx(6000),
    )


@pytest.mark.unit
def test_a_gradual_change_of_tempo_is_sampled_densely() -> None:
    score: Score = _score()
    TempoTransition.create(
        start=anchor_at(score=score, at=Fraction(0)),
        end=anchor_at(score=score, at=Fraction(1)),
        ratio=Fraction(1, 2),
    )

    (segment,) = build_projection(document=score.document).segments

    assert len(segment.moments) >= 128
    times: list[float] = [moment.time_ms for moment in segment.moments]
    assert times == sorted(times)
    assert segment.moments[64].position == Fraction(1, 2)
    assert segment.moments[64].time_ms < 0.5 * segment.moments[128].time_ms * 1.1


@pytest.mark.unit
def test_a_start_inside_the_score_cuts_the_map_at_that_place() -> None:
    score: Score = _score()
    quarters(score=score, measure=0, beats=(0, 1))

    projection: PlaybackProjection = build_projection(document=score.document, start=Fraction(1, 8))

    (segment,) = projection.segments
    assert (segment.start, segment.start_ms) == (Fraction(1, 8), 0.0)
    assert [m.position for m in segment.moments][:2] == [Fraction(1, 8), _Q]
    assert segment.moments[1].time_ms == pytest.approx(250)
    assert segment.end_ms == pytest.approx(3750)
    assert [(a.start_ms, a.end_ms) for a in projection.anchors] == [
        (pytest.approx(0), pytest.approx(250)),
        (pytest.approx(250), pytest.approx(750)),
    ]


@pytest.mark.unit
def test_a_start_at_the_end_has_no_map() -> None:
    score: Score = _score()

    projection: PlaybackProjection = build_projection(document=score.document, start=Fraction(2))

    assert projection.anchors == ()
    assert projection.segments == ()
