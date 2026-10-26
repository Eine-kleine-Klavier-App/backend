from enum import StrEnum


class PitchEditMode(StrEnum):
    """What an edit of the clefs or octave lines does to the notes it reaches."""

    # the notes move to the steps that sound as before
    PRESERVE_PITCH = "preserve_pitch"
    # the notes stay on their steps and sound different
    PRESERVE_STEP = "preserve_step"
