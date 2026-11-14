from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.context import Refrain, SustainHold
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.playback import PedalSpan, build_pedal, build_route

from ..scene import Score, anchor_at, build_score

# A measure of the scene is one whole note long. The pedal is read as (start, end) in the time
# of the route.

_ONE: Fraction = Fraction(1)

type Shape = tuple[Fraction, Fraction]


def _pedal(*, score: Score) -> list[Shape]:
    geometry: ScoreGeometry = ScoreGeometry(document=score.document)
    contexts: ContextIndex = ContextIndex(document=score.document, geometry=geometry)
    route = build_route(geometry=geometry, contexts=contexts)
    spans: list[PedalSpan] = build_pedal(route=route, geometry=geometry, contexts=contexts)

    return [(span.start, span.end) for span in spans]


@pytest.mark.unit
def test_a_score_without_a_pedal_has_none_down() -> None:
    assert _pedal(score=build_score(measure_count=2)) == []


@pytest.mark.unit
def test_a_pedal_is_down_from_its_start_to_its_end() -> None:
    score: Score = build_score(measure_count=3)
    SustainHold.create(
        start=anchor_at(score=score, at=Fraction(1, 2)),
        end=anchor_at(score=score, at=Fraction(2)),
    )

    assert _pedal(score=score) == [(Fraction(1, 2), Fraction(2))]


@pytest.mark.unit
def test_a_pedal_that_a_jump_cuts_is_lifted_there_and_pressed_again_in_the_next_pass() -> None:
    """The pedal goes down in the middle of measure two and up in the middle of measure
    three; measures one and two are repeated. The first pass lifts it at the repeat, the
    second goes on to its end."""
    score: Score = build_score(measure_count=3)
    SustainHold.create(
        start=anchor_at(score=score, at=Fraction(3, 2)),
        end=anchor_at(score=score, at=Fraction(5, 2)),
    )
    Refrain.create(
        start=anchor_at(score=score, at=Fraction(0)),
        end=anchor_at(score=score, at=Fraction(2)),
        times=2,
    )

    assert _pedal(score=score) == [
        (Fraction(3, 2), Fraction(2)),
        (Fraction(7, 2), Fraction(9, 2)),
    ]
