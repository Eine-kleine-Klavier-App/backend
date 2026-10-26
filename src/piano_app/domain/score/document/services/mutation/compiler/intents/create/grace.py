from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    Fingering,
    GracePlacement,
    GraceType,
)
from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class AddGraceNoteIntent(EditIntent):
    """Add a grace note, written as ``written_value``, to the group before or after the note of
    this carrier, after the grace carrier ``after_carrier_id`` of that group, first when none. It
    borrows its time from that note. An omitted accidental is the one in force."""

    host_carrier_id: str
    placement: GracePlacement
    grace_type: GraceType
    written_value: DottedRhythmicValue
    staff_id: str
    staff_step: int
    accidental: Accidental | None = None
    fingering: Fingering = Fingering.NONE
    after_carrier_id: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AddGraceCarrierNoteIntent(EditIntent):
    """Add a note to a grace carrier, which then holds a chord. An omitted accidental is the one
    in force."""

    carrier_id: str
    staff_id: str
    staff_step: int
    accidental: Accidental | None = None
    fingering: Fingering = Fingering.NONE


@dataclass(frozen=True, slots=True, kw_only=True)
class RemoveGraceNoteIntent(EditIntent):
    """Remove a grace note; the group goes with its last one."""

    note_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeGraceTypeIntent(EditIntent):
    """Set the kind of the group of grace notes this grace note belongs to: slashed or plain.
    The change moves the time the group takes from its note."""

    note_id: str
    grace_type: GraceType


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeGraceValueIntent(EditIntent):
    """Write a grace carrier as ``written_value``. The change moves the time its group takes from
    the note it belongs to."""

    carrier_id: str
    written_value: DottedRhythmicValue
