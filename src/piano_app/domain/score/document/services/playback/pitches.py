from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import Accidental, GracePlacement
from piano_app.domain.score.document.models.relations import Glissando
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceItem,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.geometry import Point
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import host_leaf_of
from piano_app.domain.score.document.services.pitch import SignCell
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch


def neighbour_pitch(
    *,
    note: Note,
    steps: int,
    geometry: ScoreGeometry,
    pitch: ScorePitch,
) -> int:
    """The MIDI number of the staff step ``steps`` away from a note's own, up when positive,
    on the note's staff: the sound of an ornament's auxiliary note or of a step of a glissando.

    It is read where the note stands (a grace note stands where its leaf does) and the sign is
    the one an inserted note would get there: the last sign on that step in the measure, else
    the key signature.
    """
    leaf: LeafRhythmicContainer | None = host_leaf_of(note=note)
    if leaf is None:
        raise ValueError("The note does not stand in a metric leaf.")

    cell: SignCell = SignCell.NOTE
    owner: object = note.note_carrier.owner
    if isinstance(owner, GraceItem):
        cell = (
            SignCell.BEFORE
            if owner.grace_group.placement is GracePlacement.BEFORE
            else SignCell.AFTER
        )

    point: Point = geometry.point_of(anchor=leaf.anchor)
    staff_step: int = note.staff_step + steps
    accidental: Accidental = pitch.accidental_at(
        staff=note.staff,
        point=point,
        staff_step=staff_step,
        cell=cell,
    )

    return pitch.resolve(
        staff=note.staff,
        point=point,
        staff_step=staff_step,
        accidental=accidental,
    ).midi_note


def glissando_pitches(
    *,
    glissando: Glissando,
    geometry: ScoreGeometry,
    pitch: ScorePitch,
) -> list[int]:
    """The MIDI numbers of the steps of a glissando, from its start note up or down to the
    step before its end note, one for each staff step of the start note's staff; the end note
    sounds as itself. The first is the start note's own sound, the others are read where the
    start note stands (a key change or a barline inside the glissando is not followed). An end
    note on another staff is brought onto the start note's staff by its sound.
    """
    start: Note = glissando.start
    end: Note = glissando.end
    end_step: int = end.staff_step
    if end.staff is not start.staff:
        end_leaf: LeafRhythmicContainer | None = host_leaf_of(note=end)
        if end_leaf is None:
            raise ValueError("The note does not stand in a metric leaf.")

        end_step = pitch.staff_step_for(
            staff=start.staff,
            point=geometry.point_of(anchor=end_leaf.anchor),
            midi_note=pitch.pitch_of(note=end).midi_note,
            accidental=end.accidental,
        )

    distance: int = end_step - start.staff_step
    direction: int = 1 if distance > 0 else -1
    pitches: list[int] = [pitch.pitch_of(note=start).midi_note]
    for count in range(1, abs(distance)):
        pitches.append(
            neighbour_pitch(note=start, steps=direction * count, geometry=geometry, pitch=pitch)
        )

    return pitches
