from dataclasses import dataclass

from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    TemporalAnchor,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    CreateMutationAction,
    DeleteMutationAction,
    UpdateMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateTemporalAnchorAction(CreateMutationAction[TemporalAnchor]):
    """Creates a temporal anchor at a measure position."""

    measure: Measure
    position: MeasurePosition


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteTemporalAnchorAction(DeleteMutationAction[TemporalAnchor]):
    """Deletes a temporal anchor."""


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateTemporalAnchorAction(UpdateMutationAction[TemporalAnchor]):
    """Moves a temporal anchor to another measure position."""

    measure: Measure
    position: MeasurePosition
