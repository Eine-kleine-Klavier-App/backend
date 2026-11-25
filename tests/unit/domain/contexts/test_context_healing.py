from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.context import (
    Context,
    DynamicChange,
    Hairpin,
    TempoChange,
)
from piano_app.domain.score.document.models.notation import (
    DottedRhythmicValue,
    DynamicMarking,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition
from piano_app.domain.score.document.services.contexts import ContextIndex, Scope
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.indexing import IndexLayer
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog

from ..scene import Score, anchor_at, build_score

# A context index kept live through the journal answers as one built from scratch: after each
# change delivered the way the engine delivers it, the contexts of every kind and scope and the
# pieces they cut the timeline into are the same.

_QUARTER: DottedRhythmicValue = DottedRhythmicValue(value=RhythmicValue.QUARTER)
_KINDS: tuple[type[Context], ...] = (TempoChange, DynamicChange, Hairpin)


class _Live:
    """A geometry and context index over a score, told of every change by its journal."""

    def __init__(self, *, score: Score) -> None:
        self.score: Score = score
        self.geometry: ScoreGeometry = ScoreGeometry(document=score.document)
        self.contexts: ContextIndex = ContextIndex(document=score.document, geometry=self.geometry)
        self.log: MutationLog = MutationLog()
        self.log.subscribe(IndexLayer(indexes=(self.geometry, self.contexts)))
        self.reads: int = 0

    def differences(self) -> list[str]:
        geometry: ScoreGeometry = ScoreGeometry(document=self.score.document)
        fresh: ContextIndex = ContextIndex(document=self.score.document, geometry=geometry)
        scopes: list[Scope] = [
            Scope.score(),
            Scope.of_voice(voice=self.score.voice),
            Scope.of_staff(staff=self.score.staff),
        ]
        extent: Fraction = geometry.root.extent
        found: list[str] = []
        for kind in _KINDS:
            for scope in scopes:
                label: str = f"{kind.__name__} in {scope}"
                if self.contexts.contexts_of(kind=kind, scope=scope) != fresh.contexts_of(
                    kind=kind, scope=scope
                ):
                    found.append(f"{label}: contexts")

                live_pieces = self.contexts.pieces_over(
                    kind=kind, start=Fraction(0), end=extent, scope=scope
                )
                fresh_pieces = fresh.pieces_over(
                    kind=kind, start=Fraction(0), end=extent, scope=scope
                )
                if live_pieces != fresh_pieces:
                    found.append(f"{label}: pieces")

        return found


def _warmed(*, live: _Live) -> _Live:
    assert live.differences() == []

    return live


@pytest.mark.unit
def test_a_context_created_is_found_in_its_place_among_the_others() -> None:
    live: _Live = _warmed(live=_Live(score=build_score(measure_count=3)))
    score: Score = live.score
    TempoChange.create(
        start=anchor_at(score=score, at=Fraction(2)), beat=_QUARTER, bpm=100, sink=live.log
    )
    assert live.differences() == []

    TempoChange.create(
        start=anchor_at(score=score, at=Fraction(1)), beat=_QUARTER, bpm=120, sink=live.log
    )

    assert live.differences() == []


@pytest.mark.unit
def test_a_context_detached_is_found_nowhere() -> None:
    live: _Live = _warmed(live=_Live(score=build_score(measure_count=3)))
    score: Score = live.score
    tempo: TempoChange = TempoChange.create(
        start=anchor_at(score=score, at=Fraction(1)), beat=_QUARTER, bpm=120, sink=live.log
    )
    assert live.differences() == []

    tempo.detach(sink=live.log)

    assert tempo not in live.contexts.contexts_of(kind=TempoChange, scope=Scope.score())
    assert live.differences() == []


@pytest.mark.unit
def test_a_context_moved_to_another_anchor_is_found_where_it_starts_now() -> None:
    live: _Live = _warmed(live=_Live(score=build_score(measure_count=4)))
    score: Score = live.score
    tempo: TempoChange = TempoChange.create(
        start=anchor_at(score=score, at=Fraction(1)), beat=_QUARTER, bpm=120, sink=live.log
    )
    assert live.differences() == []

    tempo.set_start(start=anchor_at(score=score, at=Fraction(3)), sink=live.log)

    assert live.differences() == []


@pytest.mark.unit
def test_an_anchor_moved_carries_the_contexts_that_start_and_end_on_it() -> None:
    live: _Live = _warmed(live=_Live(score=build_score(measure_count=4)))
    score: Score = live.score
    start = anchor_at(score=score, at=Fraction(1))
    end = anchor_at(score=score, at=Fraction(5, 2))
    Hairpin.create(start=start, end=end, voice=score.voice, steps=1, sink=live.log)
    DynamicChange.create(start=end, voice=score.voice, dynamic=DynamicMarking.FORTE, sink=live.log)
    assert live.differences() == []

    end.move_to(
        measure=score.measures[3],
        position=MeasurePosition.of_fraction(fraction=Fraction(1, 4)),
        sink=live.log,
    )

    assert live.differences() == []


@pytest.mark.unit
def test_a_measure_inserted_shifts_every_context_after_it() -> None:
    live: _Live = _warmed(live=_Live(score=build_score(measure_count=3)))
    score: Score = live.score
    TempoChange.create(
        start=anchor_at(score=score, at=Fraction(2)), beat=_QUARTER, bpm=100, sink=live.log
    )
    assert live.differences() == []

    score.document.append_measure(measure=Measure.create(), sink=live.log)

    assert live.differences() == []


@pytest.mark.unit
def test_telling_about_one_context_heals_only_that_one() -> None:
    """Two contexts of a kind change, one is told: the told one is right, the other stays as
    it was until it is told too."""
    live: _Live = _warmed(live=_Live(score=build_score(measure_count=4)))
    score: Score = live.score
    first: TempoChange = TempoChange.create(
        start=anchor_at(score=score, at=Fraction(1)), beat=_QUARTER, bpm=120, sink=live.log
    )
    second: TempoChange = TempoChange.create(
        start=anchor_at(score=score, at=Fraction(2)), beat=_QUARTER, bpm=130, sink=live.log
    )
    assert live.differences() == []

    first.detach()
    second.detach()
    live.contexts.invalidate_context(context=first)

    assert first not in live.contexts.contexts_of(kind=TempoChange, scope=Scope.score())
    assert second in live.contexts.contexts_of(kind=TempoChange, scope=Scope.score())
    live.contexts.invalidate_context(context=second)
    assert live.differences() == []
