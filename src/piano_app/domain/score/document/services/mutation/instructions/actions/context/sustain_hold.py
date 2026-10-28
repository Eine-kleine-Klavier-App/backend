from dataclasses import dataclass

from piano_app.domain.score.document.models.context import SustainHold
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    CreateMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateSustainHoldAction(CreateMutationAction[SustainHold]):
    """Creates a sustain hold on its anchors."""

    start: TemporalAnchor
    end: TemporalAnchor
