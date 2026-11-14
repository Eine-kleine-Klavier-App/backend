from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.context import SustainHold, TempoChange
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import (
    Articulation,
    DottedRhythmicValue,
    RhythmicValue,
)
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch
from piano_app.domain.score.document.services.playback import (
    PedalSpan,
    PlayedNote,
    TimedNote,
    build_pedal,
    build_route,
    build_sounds,
    build_timeline,
    expand_sounds,
    time_notes,
)

from ..scene import Score, anchor_at, build_score, note_at, quarters

# A measure of the scene is one whole note; at a quarter = 120 it takes 2000 ms and a quarter
# 500 ms.

_Q: Fraction = Fraction(1, 4)


def _score() -> Score:
    score: Score = build_score(measure_count=2)
    start = anchor_at(score=score, at=Fraction(0))
    for context in tuple(start.starting_contexts):
        if isinstance(context, TempoChange):
            context.detach()

    TempoChange.create(
        start=start,
        beat=DottedRhythmicValue(value=RhythmicValue.QUARTER),
        bpm=120,
    )
    quarters(score=score, measure=0, beats=(0,))

    return score


def _timed(*, score: Score) -> list[TimedNote]:
    """The whole pipeline, from the document to the notes in time."""
    document = score.document
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
    route = build_route(geometry=geometry, contexts=contexts)
    played: list[PlayedNote] = expand_sounds(
        sounds=build_sounds(document=document, geometry=geometry, route=route),
        document=document,
        geometry=geometry,
        pitch=ScorePitch(document=document, geometry=geometry, contexts=contexts),
    )

    return time_notes(
        notes=played,
        timeline=build_timeline(route=route, geometry=geometry, contexts=contexts),
        pedal=build_pedal(route=route, geometry=geometry, contexts=contexts),
    )


def _hold(*, score: Score, start: Fraction, end: Fraction) -> None:
    SustainHold.create(
        start=anchor_at(score=score, at=start),
        end=anchor_at(score=score, at=end),
    )


@pytest.mark.unit
def test_a_note_is_given_its_time_in_milliseconds() -> None:
    (timed,) = _timed(score=_score())

    assert (timed.pitch, timed.start_ms, timed.end_ms) == (64, pytest.approx(0), pytest.approx(500))


@pytest.mark.unit
def test_a_staccato_note_under_the_pedal_rings_until_the_pedal_goes_up() -> None:
    score: Score = _score()
    note_at(score=score, at=Fraction(0)).note_carrier.set_articulations(
        articulations=frozenset({Articulation.STACCATO})
    )
    _hold(score=score, start=Fraction(0), end=Fraction(1))

    (timed,) = _timed(score=score)

    assert timed.end_ms == pytest.approx(2000)
    assert timed.key_release_ms == pytest.approx(250)


@pytest.mark.unit
def test_a_staccato_note_without_the_pedal_stops_at_its_short_end() -> None:
    score: Score = _score()
    note_at(score=score, at=Fraction(0)).note_carrier.set_articulations(
        articulations=frozenset({Articulation.STACCATO})
    )

    (timed,) = _timed(score=score)

    assert timed.end_ms == pytest.approx(250)


def _note(*, end: Fraction) -> PlayedNote:
    score: Score = _score()
    source: Note = note_at(score=score, at=Fraction(0))

    return PlayedNote(source=source, pitch=64, start=Fraction(0), end=end)


def _times(*, end: Fraction, pedal: list[PedalSpan]) -> tuple[float, float]:
    score: Score = _score()
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)
    contexts: ContextIndex = ContextIndex(document=score.document, geometry=geometry)
    route = build_route(geometry=geometry, contexts=contexts)
    (timed,) = time_notes(
        notes=[_note(end=end)],
        timeline=build_timeline(route=route, geometry=geometry, contexts=contexts),
        pedal=pedal,
    )

    return timed.start_ms, timed.end_ms


@pytest.mark.unit
def test_a_note_ending_as_the_pedal_goes_down_or_up_is_not_prolonged() -> None:
    span: PedalSpan = PedalSpan(start=Fraction(1, 8), end=_Q)

    assert _times(end=Fraction(1, 8), pedal=[span])[1] == pytest.approx(250)
    assert _times(end=_Q, pedal=[span])[1] == pytest.approx(500)


@pytest.mark.unit
def test_a_note_ending_before_the_pedal_or_after_it_is_not_prolonged() -> None:
    span: PedalSpan = PedalSpan(start=_Q, end=Fraction(1, 2))

    assert _times(end=Fraction(1, 8), pedal=[span])[1] == pytest.approx(250)
    assert _times(end=Fraction(3, 4), pedal=[span])[1] == pytest.approx(1500)
