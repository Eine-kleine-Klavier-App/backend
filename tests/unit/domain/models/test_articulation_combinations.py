from fractions import Fraction
from itertools import combinations

import pytest

from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.models.notation import (
    ARTICULATION_CATEGORIES,
    Articulation,
    ArticulationCategory,
    check_articulations,
    with_articulation,
)

from ..scene import Score, four_quarters, note_at

# The marks of articulation a carrier may hold together: at most one of length (staccato,
# staccatissimo, tenuto, fermata), one of loudness (accent, marcato) and one of arpeggio (up,
# down).

_STACCATO: Articulation = Articulation.STACCATO
_STACCATISSIMO: Articulation = Articulation.STACCATISSIMO
_TENUTO: Articulation = Articulation.TENUTO
_ACCENT: Articulation = Articulation.ACCENT
_MARCATO: Articulation = Articulation.MARCATO
_FERMATA: Articulation = Articulation.FERMATA
_ARPEGGIO_UP: Articulation = Articulation.ARPEGGIO_UP
_ARPEGGIO_DOWN: Articulation = Articulation.ARPEGGIO_DOWN

_LENGTH: list[Articulation] = [_STACCATO, _STACCATISSIMO, _TENUTO, _FERMATA]
_LOUDNESS: list[Articulation] = [_ACCENT, _MARCATO]
_ARPEGGIO: list[Articulation] = [_ARPEGGIO_UP, _ARPEGGIO_DOWN]


@pytest.mark.unit
def test_every_mark_belongs_to_one_category() -> None:
    assert set(ARTICULATION_CATEGORIES) == set(Articulation)
    assert {
        mark
        for mark in Articulation
        if ARTICULATION_CATEGORIES[mark] is ArticulationCategory.LENGTH
    } == set(_LENGTH)
    assert {
        mark
        for mark in Articulation
        if ARTICULATION_CATEGORIES[mark] is ArticulationCategory.LOUDNESS
    } == set(_LOUDNESS)
    assert {
        mark
        for mark in Articulation
        if ARTICULATION_CATEGORIES[mark] is ArticulationCategory.ARPEGGIO
    } == set(_ARPEGGIO)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("first", "second", "category"),
    [(a, b, "length") for a, b in combinations(_LENGTH, 2)]
    + [(a, b, "loudness") for a, b in combinations(_LOUDNESS, 2)]
    + [(a, b, "arpeggio") for a, b in combinations(_ARPEGGIO, 2)],
)
def test_two_marks_of_one_category_are_refused_in_either_order(
    first: Articulation, second: Articulation, category: str
) -> None:
    for marks in ({first, second}, {second, first}):
        with pytest.raises(ValueError, match=f"both marks of {category}"):
            check_articulations(articulations=marks)


@pytest.mark.unit
@pytest.mark.parametrize("length", [None, *_LENGTH])
@pytest.mark.parametrize("loudness", [None, *_LOUDNESS])
@pytest.mark.parametrize("arpeggio", [None, *_ARPEGGIO])
def test_one_mark_of_each_category_is_allowed(
    length: Articulation | None, loudness: Articulation | None, arpeggio: Articulation | None
) -> None:
    check_articulations(
        articulations={mark for mark in (length, loudness, arpeggio) if mark is not None}
    )


@pytest.mark.unit
def test_forty_five_of_the_two_hundred_fifty_six_sets_of_marks_are_allowed() -> None:
    allowed: int = 0
    for size in range(len(Articulation) + 1):
        for marks in combinations(Articulation, size):
            try:
                check_articulations(articulations=set(marks))
            except ValueError:
                continue

            allowed += 1

    assert allowed == 45


@pytest.mark.unit
def test_a_mark_put_on_replaces_the_mark_of_its_category_and_keeps_the_other() -> None:
    assert with_articulation(current={_ACCENT, _STACCATO}, added=_MARCATO) == {
        _MARCATO,
        _STACCATO,
    }
    assert with_articulation(current={_STACCATO, _ACCENT}, added=_FERMATA) == {
        _FERMATA,
        _ACCENT,
    }
    assert with_articulation(current={_TENUTO}, added=_STACCATO) == {_STACCATO}
    assert with_articulation(current=set(), added=_TENUTO) == {_TENUTO}
    assert with_articulation(current={_TENUTO}, added=_TENUTO) == {_TENUTO}


@pytest.mark.unit
def test_a_carrier_refuses_two_marks_of_a_category_and_keeps_its_marks() -> None:
    score: Score = four_quarters()
    carrier: NoteCarrier = note_at(score=score, at=Fraction(0)).note_carrier
    carrier.set_articulations(articulations=frozenset({_ACCENT}))

    with pytest.raises(ValueError, match="both marks of loudness"):
        carrier.set_articulations(articulations=frozenset({_ACCENT, _MARCATO}))

    assert carrier.articulations == {_ACCENT}
