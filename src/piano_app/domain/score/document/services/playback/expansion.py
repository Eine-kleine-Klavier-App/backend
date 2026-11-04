from collections.abc import Sequence
from dataclasses import dataclass, replace
from fractions import Fraction

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import Articulation, GracePlacement
from piano_app.domain.score.document.models.relations import Glissando
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceGroup,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import host_leaf_of, sounding_of
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch

from .lengths import LENGTH_SHARES
from .ornaments import Piece, ornament_pieces
from .pitches import glissando_pitches, neighbour_pitch
from .played import GLISSANDO_SHARE, ORNAMENT_UNIT, PlayedNote
from .sounds import RestHost, Sound, SoundPart


@dataclass(frozen=True, slots=True, kw_only=True)
class _Attack:
    """A sound that begins at a carrier, with where it starts and ends once what stands
    before it has moved it."""

    sound: Sound
    start: Fraction
    end: Fraction

    @property
    def source(self) -> Note:
        return self.sound.parts[0].note


def _grace_lengths(*, group: GraceGroup) -> list[Fraction]:
    """How long each grace note of a group sounds."""
    return [
        sounding_of(group=group, written=item.rhythmic_value.fraction) for item in group.grace_items
    ]


def _grace_notes(
    *,
    group: GraceGroup,
    lengths: Sequence[Fraction],
    cursor: Fraction,
    pitch: ScorePitch,
) -> list[PlayedNote]:
    """The notes of a group, one after another from ``cursor``; a rest among them is a silence."""
    notes: list[PlayedNote] = []
    for item, length in zip(group.grace_items, lengths, strict=True):
        if isinstance(item.carrier, NoteCarrier):
            for grace_note in item.carrier.notes:
                notes.append(
                    PlayedNote(
                        source=grace_note,
                        pitch=pitch.pitch_of(note=grace_note).midi_note,
                        start=cursor,
                        end=cursor + length,
                    )
                )

        cursor += length

    return notes


def expand_sounds(
    *,
    sounds: Sequence[Sound],
    document: ScoreDocument,
    geometry: ScoreGeometry,
    pitch: ScorePitch,
    rests: Sequence[RestHost] = (),
) -> list[PlayedNote]:
    """The plain notes the sounds are played as, in the order they start.

    The sounds that begin at one carrier at one time are its new notes (a note that only
    continues a tie begins nothing), and the marks of the carrier act on them together: the
    room an ornament or an arpeggio has is the shortest of their lengths, and the last note of
    an expansion lasts to the end of its own sound. The grace notes of a leaf are played
    first: those before it from its start, which moves the start of its new notes, those after
    it ending where it ends, which moves the end of the sounds that end there; on a leaf in
    the middle of a tie they sound over the held note. The mark of length of the carrier
    then shortens each new sound to its share of what is left, and the shortened end is the
    end the rest works with. An arpeggio starts the notes one after
    another by the place of their staff steps on the page, each held to the end; a glissando
    from a note divides its sound equally among its steps and takes the place of the ornament.
    """
    groups: dict[tuple[NoteCarrier, Fraction], list[Sound]] = {}
    for sound in sounds:
        key: tuple[NoteCarrier, Fraction] = (sound.parts[0].note.note_carrier, sound.start)
        groups.setdefault(key, []).append(sound)

    played: list[PlayedNote] = []
    graces_played: set[tuple[LeafRhythmicContainer, Fraction, GracePlacement]] = set()
    for (carrier, _), group in groups.items():
        attacks: list[_Attack] = [
            _Attack(sound=sound, start=sound.start, end=sound.end) for sound in group
        ]
        for position, attack in enumerate(attacks):
            start: Fraction = attack.start
            end: Fraction = attack.end
            for part_index, part in enumerate(attack.sound.parts):
                leaf: LeafRhythmicContainer | None = host_leaf_of(note=part.note)
                if leaf is None:
                    continue

                grace: GraceGroup | None
                for grace in (leaf.grace_before, leaf.grace_after):
                    if grace is None:
                        continue

                    lengths: list[Fraction] = _grace_lengths(group=grace)
                    taken: Fraction = sum(lengths, Fraction(0))
                    before: bool = grace.placement is GracePlacement.BEFORE
                    done: tuple[LeafRhythmicContainer, Fraction, GracePlacement] = (
                        leaf,
                        part.start,
                        grace.placement,
                    )
                    if done not in graces_played:
                        graces_played.add(done)
                        played.extend(
                            _grace_notes(
                                group=grace,
                                lengths=lengths,
                                cursor=part.start if before else part.end - taken,
                                pitch=pitch,
                            )
                        )

                    if before and part_index == 0:
                        start += taken

                    if not before and part_index == len(attack.sound.parts) - 1:
                        end -= taken

            attacks[position] = replace(attack, start=start, end=end)

        kept: Fraction = Fraction(1)
        for mark, mark_share in LENGTH_SHARES.items():
            if mark in carrier.articulations:
                kept = mark_share

        if kept != 1:
            for position, attack in enumerate(attacks):
                attacks[position] = replace(
                    attack,
                    end=attack.start + kept * (attack.end - attack.start),
                )

        room: Fraction = min(attack.end - attack.start for attack in attacks)

        direction: Articulation | None = None
        for mark in (Articulation.ARPEGGIO_UP, Articulation.ARPEGGIO_DOWN):
            if mark in carrier.articulations:
                direction = mark

        if direction is not None:
            # lower staff first (the last of the document's staffs), then from the bottom up
            ordered: list[_Attack] = sorted(
                attacks,
                key=lambda attack: (
                    -document.staffs.index(attack.source.staff),
                    attack.source.staff_step,
                ),
            )
            if direction is Articulation.ARPEGGIO_DOWN:
                ordered.reverse()

            step: Fraction = min(ORNAMENT_UNIT, room / len(ordered))
            attacks = [
                replace(attack, start=attack.start + index * step)
                for index, attack in enumerate(ordered)
            ]
            room = min(attack.end - attack.start for attack in attacks)

        for attack in attacks:
            glissando: Glissando | None = None
            for sounding in attack.sound.notes:
                for relation in sounding.relations:
                    if isinstance(relation, Glissando) and relation.start is sounding:
                        glissando = relation

            if glissando is not None:
                steps: list[int] = glissando_pitches(
                    glissando=glissando,
                    geometry=geometry,
                    pitch=pitch,
                )
                # the note sounds as itself first; the steps share the last part of its own stretch
                # (of the last note of a tied chain, whose stretch is the glissando's start)
                own: SoundPart = next(
                    part for part in attack.sound.parts if part.note is glissando.start
                )
                window: Fraction = min(
                    attack.end - attack.start, GLISSANDO_SHARE * (own.end - own.start)
                )
                share: Fraction = window / len(steps)
                slide_from: Fraction = attack.end - window
                for index, step_pitch in enumerate(steps):
                    played.append(
                        PlayedNote(
                            source=attack.source,
                            pitch=step_pitch,
                            start=attack.start if index == 0 else slide_from + index * share,
                            end=slide_from + (index + 1) * share,
                        )
                    )

                continue

            piece: Piece
            for piece in ornament_pieces(
                ornament=carrier.ornament,
                start=attack.start,
                end=attack.end,
                room=room,
            ):
                midi_note: int = (
                    pitch.pitch_of(note=attack.source).midi_note
                    if piece.steps == 0
                    else neighbour_pitch(
                        note=attack.source,
                        steps=piece.steps,
                        geometry=geometry,
                        pitch=pitch,
                    )
                )
                played.append(
                    PlayedNote(
                        source=attack.source,
                        pitch=midi_note,
                        start=piece.start,
                        end=piece.end,
                    )
                )

    for host in rests:
        for rest_grace in (host.leaf.grace_before, host.leaf.grace_after):
            if rest_grace is None:
                continue

            rest_lengths: list[Fraction] = _grace_lengths(group=rest_grace)
            played.extend(
                _grace_notes(
                    group=rest_grace,
                    lengths=rest_lengths,
                    cursor=host.start
                    if rest_grace.placement is GracePlacement.BEFORE
                    else host.end - sum(rest_lengths, Fraction(0)),
                    pitch=pitch,
                )
            )

    played.sort(key=lambda note: note.start)

    return played
