from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Pitch:
    """Resolved chromatic height, numbered like MIDI.

    Resolution does not impose a playback device's range or clamp transpositions.
    """

    midi_note: int
