from dataclasses import dataclass

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.shared.abstract import abstract


@abstract
@dataclass(frozen=True, slots=True, kw_only=True)
class MutationAction:
    """Role base: a terminal work item executed by its handler.

    Actions are dumb data records — inputs hold live entities; all behavior lives in the
    matching handler.
    """


@abstract
@dataclass(frozen=True, slots=True, kw_only=True)
class CreateMutationAction[T: ScoreEntity](MutationAction):
    """An action that creates an entity of type ``T``; its handler returns it."""


@abstract
@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteMutationAction[T: ScoreEntity](MutationAction):
    """An action that removes an existing ``target``."""

    target: T


@abstract
@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateMutationAction[T: ScoreEntity](MutationAction):
    """An action that mutates an existing ``target`` in place."""

    target: T
