from enum import StrEnum


class Ornament(StrEnum):
    NONE = "none"
    TRILL = "trill"
    UPPER_MORDENT = "upper_mordent"
    LOWER_MORDENT = "lower_mordent"
    TURN = "turn"
    INVERTED_TURN = "inverted_turn"
    TREMOLO_1 = "tremolo_1"
    TREMOLO_2 = "tremolo_2"
    TREMOLO_3 = "tremolo_3"
