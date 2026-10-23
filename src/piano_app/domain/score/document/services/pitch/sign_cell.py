from enum import IntEnum


class SignCell(IntEnum):
    """Where among the signs of one coordinate a sign stands, in the order they are read:
    the grace notes before the note, the notes of every voice, the grace notes after."""

    BEFORE = 0
    NOTE = 1
    AFTER = 2
