from enum import StrEnum


class DynamicMarking(StrEnum):
    PIANISSIMISSIMO = "ppp"
    PIANISSIMO = "pp"
    PIANO = "p"
    MEZZO_PIANO = "mp"
    MEZZO_FORTE = "mf"
    FORTE = "f"
    FORTISSIMO = "ff"
    FORTISSIMISSIMO = "fff"

    @property
    def level(self) -> int:
        """The place on the scale from the softest (0) to the loudest."""
        return _LEVELS.index(self)

    @classmethod
    def at_level(cls, level: int) -> DynamicMarking:
        """The marking at a place on the scale, held to the softest and the loudest."""
        return _LEVELS[min(max(level, 0), len(_LEVELS) - 1)]


_LEVELS: tuple[DynamicMarking, ...] = tuple(DynamicMarking)
