from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.notation import RhythmicValue
from piano_app.domain.score.document.models.structural import MeasurePosition, Voice
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.helpers import find_container_at

from ..scene import Score, anchor_at, build_score, group, note, size


def _find(
    *, score: Score, at: Fraction, scope: RhythmicContainerParent
) -> RhythmicContainer | None:
    return find_container_at(
        measure=score.measures[int(at)],
        position=MeasurePosition.of_fraction(fraction=at - int(at)),
        scope=scope,
    )


@pytest.mark.unit
def test_each_scope_sees_only_its_own_container_at_a_shared_anchor() -> None:
    """A group, a group nested in it and a leaf nested in that start at one instant: the
    voice finds the outer group, the outer group finds the inner one, the inner one finds
    the leaf."""
    score: Score = build_score(bars=1)
    outer: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    inner: GroupRhythmicContainer = group(
        score=score,
        parent=outer,
        at=Fraction(0),
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
    )
    leaf: LeafRhythmicContainer = note(
        score=score,
        parent=inner,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.SIXTEENTH,
        step=0,
    )

    assert _find(score=score, at=Fraction(0), scope=score.voice) is outer
    assert _find(score=score, at=Fraction(0), scope=outer) is inner
    assert _find(score=score, at=Fraction(0), scope=inner) is leaf


@pytest.mark.unit
def test_a_leaf_inside_a_group_is_not_found_from_the_voice() -> None:
    score: Score = build_score(bars=1)
    triplet: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    second: LeafRhythmicContainer = note(
        score=score,
        parent=triplet,
        at=Fraction(1, 12),
        rhythmic_value=RhythmicValue.EIGHTH,
        step=0,
    )

    assert _find(score=score, at=Fraction(1, 12), scope=score.voice) is None
    assert _find(score=score, at=Fraction(1, 12), scope=triplet) is second


@pytest.mark.unit
def test_another_voices_container_at_the_same_anchor_is_not_found() -> None:
    score: Score = build_score(bars=1)
    other: Voice = Voice()
    note(score=score, parent=other, at=Fraction(0), rhythmic_value=RhythmicValue.HALF, step=0)

    assert _find(score=score, at=Fraction(0), scope=score.voice) is None


@pytest.mark.unit
def test_an_empty_slot_has_no_container() -> None:
    score: Score = build_score(bars=1)

    assert _find(score=score, at=Fraction(1, 4), scope=score.voice) is None


@pytest.mark.unit
def test_two_containers_of_one_scope_at_one_anchor_are_a_broken_model() -> None:
    """Siblings never overlap — displacement keeps it so. Built by hand past the
    analyzers, the lookup refuses to pick one."""
    score: Score = build_score(bars=1)
    for _ in range(2):
        LeafRhythmicContainer.create(
            parent=score.voice,
            anchor=anchor_at(score=score, at=Fraction(0)),
            size=size(RhythmicValue.QUARTER),
        )

    with pytest.raises(ValueError, match="Multiple containers"):
        _find(score=score, at=Fraction(0), scope=score.voice)
