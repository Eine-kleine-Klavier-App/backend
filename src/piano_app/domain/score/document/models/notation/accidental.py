from enum import StrEnum
from typing import Literal


class Accidental(StrEnum):
    """A note's own explicit accidental. Always a concrete, authored value; never
    inferred or left unspecified on a live ``Note``."""

    FLAT = "flat"
    NATURAL = "natural"
    SHARP = "sharp"


type KeySignatureAccidental = Literal[Accidental.FLAT, Accidental.SHARP]
