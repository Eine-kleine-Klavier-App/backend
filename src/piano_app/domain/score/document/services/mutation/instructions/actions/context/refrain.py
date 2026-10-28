from dataclasses import dataclass

from piano_app.domain.score.document.models.context import Refrain
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    CreateMutationAction,
    UpdateMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateRefrainAction(CreateMutationAction[Refrain]):
    """Creates a refrain on its anchors; no end anchor lasts until the end of the score."""

    start: TemporalAnchor
    end: TemporalAnchor | None
    times: int


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateRefrainTimesAction(UpdateMutationAction[Refrain]):
    """Changes how many times a refrain is played."""

    times: int


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateRefrainStartAction(UpdateMutationAction[Refrain]):
    """Moves a refrain's start to another anchor."""

    start: TemporalAnchor


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateRefrainEndAction(UpdateMutationAction[Refrain]):
    """Moves a refrain's end to another anchor, or to the end of the score."""

    end: TemporalAnchor | None
