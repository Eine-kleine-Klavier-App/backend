from dataclasses import dataclass
from fractions import Fraction
from typing import ClassVar

from piano_app.domain.score.document.models.notation import Accidental, Fingering
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    Staff,
    Voice,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    MutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class NoteContent:
    """What every piece of a placed note holds: one note of this pitch, on this staff."""

    staff: Staff
    staff_step: int
    accidental: Accidental
    fingering: Fingering = Fingering.NONE


@dataclass(frozen=True, slots=True, kw_only=True)
class RestContent:
    """What every piece of a placed rest holds: a rest on this staff."""

    staff: Staff


@dataclass(frozen=True, slots=True, kw_only=True)
class PlaceSpansRequest(MutationRequest):
    """A request to place a new rhythmic item of ``written_length`` starting at
    ``position`` in ``measure`` of ``voice``: where its spans lie, and what happens to the
    spans it meets. ``written_length`` is read in the units of the scope holding the
    start."""

    axis: ClassVar[Axis | None] = Axis.FRAMES

    voice: Voice
    measure: Measure
    position: MeasurePosition
    written_length: Fraction
    content: NoteContent | RestContent
