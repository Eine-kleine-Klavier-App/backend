from dataclasses import dataclass

from piano_app.domain.score.document.models.context import NewFragment, Volta
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    CreateMutationAction,
    UpdateMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateVoltaAction(CreateMutationAction[Volta]):
    """Creates a volta on its anchors: the body from ``start`` to ``body_end`` and the
    fragments after it."""

    start: TemporalAnchor
    body_end: TemporalAnchor
    fragments: tuple[NewFragment, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ReshapeVoltaAction(UpdateMutationAction[Volta]):
    """Gives a volta another body and other fragments, keeping the volta itself."""

    start: TemporalAnchor
    body_end: TemporalAnchor
    fragments: tuple[NewFragment, ...]
