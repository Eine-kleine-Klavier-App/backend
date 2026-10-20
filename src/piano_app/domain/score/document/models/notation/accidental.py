from enum import StrEnum


class Accidental(StrEnum):
    """A note's own explicit accidental. Always a concrete, authored value; never
    inferred or left unspecified on a live ``Note``."""

    DOUBLE_FLAT = "double_flat"
    FLAT = "flat"
    NATURAL = "natural"
    SHARP = "sharp"
    DOUBLE_SHARP = "double_sharp"
