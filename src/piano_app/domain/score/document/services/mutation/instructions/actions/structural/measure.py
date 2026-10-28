from dataclasses import dataclass

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.notation import RhythmicSize
from piano_app.domain.score.document.models.structural import Measure
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    CreateMutationAction,
    DeleteMutationAction,
    UpdateMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateMeasureAction(CreateMutationAction[Measure]):
    """Creates a measure right before ``before``, or after the last one when it is None."""

    document: ScoreDocument
    before: Measure | None
    time_signature: RhythmicSize


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteMeasureAction(DeleteMutationAction[Measure]):
    """Removes a measure from the document's chain."""

    document: ScoreDocument


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateMeasureTimeSignatureAction(UpdateMutationAction[Measure]):
    """Gives a measure another time signature."""

    time_signature: RhythmicSize
