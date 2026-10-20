from collections.abc import Collection
from enum import StrEnum


class Articulation(StrEnum):
    STACCATO = "staccato"
    STACCATISSIMO = "staccatissimo"
    TENUTO = "tenuto"
    ACCENT = "accent"
    MARCATO = "marcato"
    FERMATA = "fermata"
    ARPEGGIO_UP = "arpeggio_up"
    ARPEGGIO_DOWN = "arpeggio_down"


class ArticulationCategory(StrEnum):
    LENGTH = "length"
    LOUDNESS = "loudness"
    ARPEGGIO = "arpeggio"


# A carrier has at most one mark of each category. A new mark, or a new category, is a row here.
ARTICULATION_CATEGORIES: dict[Articulation, ArticulationCategory] = {
    Articulation.STACCATO: ArticulationCategory.LENGTH,
    Articulation.STACCATISSIMO: ArticulationCategory.LENGTH,
    Articulation.TENUTO: ArticulationCategory.LENGTH,
    Articulation.FERMATA: ArticulationCategory.LENGTH,
    Articulation.ACCENT: ArticulationCategory.LOUDNESS,
    Articulation.MARCATO: ArticulationCategory.LOUDNESS,
    Articulation.ARPEGGIO_UP: ArticulationCategory.ARPEGGIO,
    Articulation.ARPEGGIO_DOWN: ArticulationCategory.ARPEGGIO,
}


def check_articulations(*, articulations: Collection[Articulation]) -> None:
    """Refuse a set of marks that holds two of one category."""
    seen: dict[ArticulationCategory, Articulation] = {}
    for articulation in Articulation:
        if articulation not in articulations:
            continue

        category: ArticulationCategory = ARTICULATION_CATEGORIES[articulation]
        if category in seen:
            raise ValueError(
                f"{seen[category].value} and {articulation.value} are both marks of "
                f"{category.value}; a carrier has one."
            )

        seen[category] = articulation


def with_articulation(
    *,
    current: Collection[Articulation],
    added: Articulation,
) -> frozenset[Articulation]:
    """The marks after ``added`` is put on a carrier that has ``current``: the mark of its
    category that stood there is replaced by it."""
    category: ArticulationCategory = ARTICULATION_CATEGORIES[added]
    kept: set[Articulation] = set()
    for articulation in current:
        if ARTICULATION_CATEGORIES[articulation] is not category:
            kept.add(articulation)

    kept.add(added)

    return frozenset(kept)
