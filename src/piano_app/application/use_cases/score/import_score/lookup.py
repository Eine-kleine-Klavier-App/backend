from collections.abc import Iterator
from fractions import Fraction

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.structural import Measure
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
)
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch

# Where a leaf stands: its voice, its measure, and its position in the measure in whole notes.
LeafKey = tuple[int, int, Fraction]

# Where a note stands: its voice, its staff, its measure, its position and its MIDI number.
NoteKey = tuple[int, int, int, Fraction, int]


def leaves_of(*, container: RhythmicContainer) -> Iterator[LeafRhythmicContainer]:
    """The leaves of a voice or a tuplet, in order, whatever the tuplets nest."""
    if isinstance(container, LeafRhythmicContainer):
        yield container
        return

    if isinstance(container, GroupRhythmicContainer):
        for child in container.children:
            yield from leaves_of(container=child)


def leaf_index(*, document: ScoreDocument) -> dict[LeafKey, LeafRhythmicContainer]:
    """Every leaf of the document by its place."""
    measure_numbers: dict[Measure, int] = {
        measure: number for number, measure in enumerate(document.measures)
    }
    found: dict[LeafKey, LeafRhythmicContainer] = {}
    for voice_index, voice in enumerate(document.voices):
        for child in voice.children:
            for leaf in leaves_of(container=child):
                key: LeafKey = (
                    voice_index,
                    measure_numbers[leaf.anchor.measure],
                    leaf.anchor.position.value,
                )
                found[key] = leaf

    return found


def note_index(*, document: ScoreDocument, pitch: ScorePitch) -> dict[NoteKey, Note]:
    """Every note of the document by its place and its sounding pitch."""
    found: dict[NoteKey, Note] = {}
    for key, leaf in leaf_index(document=document).items():
        if not isinstance(leaf.carrier, NoteCarrier):
            continue

        for note in leaf.carrier.notes:
            found[
                (
                    key[0],
                    document.staffs.index(note.staff),
                    key[1],
                    key[2],
                    pitch.pitch_of(note=note).midi_note,
                )
            ] = note

    return found
