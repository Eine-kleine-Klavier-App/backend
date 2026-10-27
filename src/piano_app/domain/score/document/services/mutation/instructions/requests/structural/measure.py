from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.notation import RhythmicSize
from piano_app.domain.score.document.models.structural import Measure
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
    DeleteMutationRequest,
    MutationRequest,
    UpdateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateEmptyMeasureRequest(CreateMutationRequest[Measure]):
    """A request to add an empty measure of ``time_signature`` to ``document`` right before
    ``before``, or after the last measure when ``before`` is None. It splits nothing at its
    barline: whoever issues it has decided what crosses there."""

    axis: ClassVar[Axis | None] = Axis.FRAMES
    creates: ClassVar[type[ScoreEntity]] = Measure

    document: ScoreDocument
    before: Measure | None
    time_signature: RhythmicSize


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteEmptyMeasureRequest(DeleteMutationRequest[Measure]):
    """A request to remove a measure of ``document`` that holds no anchor."""

    axis: ClassVar[Axis | None] = Axis.FRAMES

    document: ScoreDocument


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateMeasureTimeSignatureRequest(UpdateMutationRequest[Measure]):
    """A request to give a measure another time signature, keeping it and its anchors;
    every anchor in it must already lie inside the new length."""

    axis: ClassVar[Axis | None] = Axis.FRAMES

    time_signature: RhythmicSize


@dataclass(frozen=True, slots=True, kw_only=True)
class RebarMeasuresRequest(MutationRequest):
    """A request to give ``measures`` of ``document`` — contiguous, in score order —
    ``time_signature`` and move their barlines: everything in them keeps its time from
    their start, and they become as many measures as their total length needs, rounded up
    — added after them or removed from their end. Nothing in them may cross their
    edges."""

    axis: ClassVar[Axis | None] = Axis.FRAMES

    document: ScoreDocument
    measures: tuple[Measure, ...]
    time_signature: RhythmicSize
