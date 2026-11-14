from fractions import Fraction

import pytest
from tests.unit.domain.document_builders import anchor

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import NewFragment, Refrain, Volta
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.playback import build_route

# Measure k of a score of whole-note measures lies on the timeline from k to k + 1. A refrain
# is given by the measure it starts at and the measure it ends at the start of (None: the end
# of the score); a volta by the measure its body starts at, the one it ends at the start of and
# its fragments, each by the measure it ends at the start of and its passes. The route is read
# as (start, end) measure numbers, each played after the one before it.

type Route = list[tuple[int, int]]


def _document(*, measures: int) -> ScoreDocument:
    return ScoreDocument.create_fresh(voice_count=1, staff_count=1, measure_count=measures)


def _refrain(*, document: ScoreDocument, first: int, last: int | None, times: int = 2) -> None:
    Refrain.create(
        start=anchor(document, Fraction(first)),
        end=None if last is None else anchor(document, Fraction(last)),
        times=times,
    )


def _volta(
    *,
    document: ScoreDocument,
    first: int,
    body_end: int,
    fragments: list[tuple[int | None, set[int]]],
) -> None:
    Volta.create(
        start=anchor(document, Fraction(first)),
        body_end=anchor(document, Fraction(body_end)),
        fragments=[
            NewFragment(
                end=None if end is None else anchor(document, Fraction(end)),
                passes=frozenset(passes),
            )
            for end, passes in fragments
        ],
    )


def _route(*, document: ScoreDocument) -> Route:
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    route: Route = []
    for segment in build_route(
        geometry=geometry,
        contexts=ContextIndex(document=document, geometry=geometry),
    ):
        assert segment.start.denominator == segment.end.denominator == 1
        route.append((int(segment.start), int(segment.end)))

    return route


@pytest.mark.unit
def test_a_score_without_repeats_is_played_once_from_start_to_end() -> None:
    document: ScoreDocument = _document(measures=4)

    assert _route(document=document) == [(0, 4)]


@pytest.mark.unit
def test_a_refrain_is_played_again_and_the_music_after_it_follows() -> None:
    """|: 1 2 :| 3 — measures 0 to 3, then 1 and 2 again and the rest in one stretch."""
    document: ScoreDocument = _document(measures=4)
    _refrain(document=document, first=1, last=3)

    assert _route(document=document) == [(0, 3), (1, 4)]


@pytest.mark.unit
def test_a_refrain_played_three_times_goes_back_twice() -> None:
    document: ScoreDocument = _document(measures=4)
    _refrain(document=document, first=1, last=3, times=3)

    assert _route(document=document) == [(0, 3), (1, 3), (1, 4)]


@pytest.mark.unit
def test_a_refrain_with_no_end_lasts_until_the_end_of_the_score() -> None:
    """|: 1 2 :|| — the closing sign stands at the end of the piece."""
    document: ScoreDocument = _document(measures=3)
    _refrain(document=document, first=1, last=None)

    assert _route(document=document) == [(0, 3), (1, 3)]


@pytest.mark.unit
def test_each_ending_is_played_in_its_own_pass() -> None:
    """|: 1 | [1. 2 :| [2. 3 :| [3. 4 — the body, then one ending a pass."""
    document: ScoreDocument = _document(measures=4)
    _volta(document=document, first=0, body_end=1, fragments=[(2, {1}), (3, {2})])

    assert _route(document=document) == [(0, 2), (0, 1), (2, 3), (0, 1), (3, 4)]


@pytest.mark.unit
def test_an_ending_for_several_passes_is_played_in_each_of_them() -> None:
    """[1., 3. and [2., four passes: 1 2 | 1 3 | 1 2 | 1 4."""
    document: ScoreDocument = _document(measures=4)
    _volta(document=document, first=0, body_end=1, fragments=[(2, {1, 3}), (3, {2})])

    assert _route(document=document) == [(0, 2), (0, 1), (2, 3), (0, 2), (0, 1), (3, 4)]


@pytest.mark.unit
def test_the_last_ending_may_last_to_the_end_of_the_score() -> None:
    document: ScoreDocument = _document(measures=3)
    _volta(document=document, first=0, body_end=1, fragments=[(2, {1}), (None, {2})])

    assert _route(document=document) == [(0, 2), (0, 1), (2, 3), (0, 1)]


@pytest.mark.unit
def test_a_refrain_inside_a_refrain_is_played_as_written_every_time_it_is_entered() -> None:
    """|: 1 |: 2 3 :| 4 :| 5 — the inner one twice in each pass of the outer one."""
    document: ScoreDocument = _document(measures=5)
    _refrain(document=document, first=0, last=4)
    _refrain(document=document, first=1, last=3)

    assert _route(document=document) == [(0, 3), (1, 4), (0, 3), (1, 5)]


@pytest.mark.unit
@pytest.mark.parametrize("spans", [[(1, 5), (1, 2)], [(1, 2), (1, 5)]])
def test_a_refrain_starting_where_a_bigger_one_starts_is_played_as_written_every_time(
    spans: list[tuple[int, int]],
) -> None:
    """1 |: |: 2 :| 3 4 5 :| 6 7 8 — both signs at the start of measure 2, however they were made:
    2 2 3 4 5, then 2 2 3 4 5 again, the inner one twice in each pass of the outer one."""
    document: ScoreDocument = _document(measures=8)
    for first, last in spans:
        _refrain(document=document, first=first, last=last)

    assert _route(document=document) == [(0, 2), (1, 5), (1, 2), (1, 8)]


@pytest.mark.unit
def test_a_refrain_inside_an_ending_is_played_as_written() -> None:
    """|: 1 | [1. |: 2 :| 3 :| [2. 4 — the inner one inside the first ending."""
    document: ScoreDocument = _document(measures=4)
    _volta(document=document, first=0, body_end=1, fragments=[(3, {1})])
    _refrain(document=document, first=1, last=2)

    assert _route(document=document) == [(0, 2), (1, 3), (0, 1), (3, 4)]


@pytest.mark.unit
def test_two_refrains_in_a_row_are_played_one_after_the_other() -> None:
    """|: 1 :||: 2 :| 3 — 1 1 2 2 3, not 1 2 1 2 3."""
    document: ScoreDocument = _document(measures=3)
    _refrain(document=document, first=0, last=1)
    _refrain(document=document, first=1, last=2)

    assert _route(document=document) == [(0, 1), (0, 2), (1, 3)]


@pytest.mark.unit
def test_jumps_that_never_let_the_score_reach_its_end_are_refused() -> None:
    document: ScoreDocument = _document(measures=2)
    _refrain(document=document, first=0, last=1, times=20_000)

    with pytest.raises(ValueError, match="never let it reach"):
        _route(document=document)
