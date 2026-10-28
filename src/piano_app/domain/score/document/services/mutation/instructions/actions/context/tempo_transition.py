from dataclasses import dataclass
from fractions import Fraction

from piano_app.domain.score.document.models.context import TempoTransition
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    CreateMutationAction,
    UpdateMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateTempoTransitionAction(CreateMutationAction[TempoTransition]):
    """Creates a tempo transition on its anchors."""

    start: TemporalAnchor
    end: TemporalAnchor
    ratio: Fraction


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateTempoTransitionRatioAction(UpdateMutationAction[TempoTransition]):
    """Changes the ratio of speed a tempo transition ends at."""

    ratio: Fraction
