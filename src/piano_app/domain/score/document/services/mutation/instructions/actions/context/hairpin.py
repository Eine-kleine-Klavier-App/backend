from dataclasses import dataclass

from piano_app.domain.score.document.models.context import Hairpin
from piano_app.domain.score.document.models.structural import TemporalAnchor, Voice
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    CreateMutationAction,
    UpdateMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateHairpinAction(CreateMutationAction[Hairpin]):
    """Creates a hairpin on its anchors."""

    start: TemporalAnchor
    end: TemporalAnchor
    voices: tuple[Voice, ...]
    steps: int


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateHairpinStepsAction(UpdateMutationAction[Hairpin]):
    """Changes by how many dynamic levels a hairpin moves."""

    steps: int
