from dataclasses import dataclass
from enum import IntEnum
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.shared.abstract import abstract


class Axis(IntEnum):
    """The level a request's analyzer owns, top-down: an axis is analysed only after the
    axes above it have executed, so a lower value ranks higher.

    ``INTENT`` ranks above every axis: an orchestration request from the compiler that
    only yields axis requests in order and decides nothing. ``CONTEXTS`` is outside the
    rhythm rank: neither it nor the rhythm axes may yield the other.
    """

    INTENT = 0
    FRAMES = 1
    SPANS = 2
    CONTENT = 3
    RELATIONS = 4
    CONTEXTS = 5


@abstract
@dataclass(frozen=True, slots=True, kw_only=True)
class MutationRequest:
    """Role base: a work item expanded by its analyzer.

    Every concrete request sets ``axis`` in its own body; ``None`` marks a request that
    belongs to no axis (anchors: storage shared by spans and contexts). The base leaves
    it unset, so a forgotten tag fails rather than inheriting one.
    """

    axis: ClassVar[Axis | None]


@abstract
@dataclass(frozen=True, slots=True, kw_only=True)
class CreateMutationRequest[T: ScoreEntity](MutationRequest):
    """A request for an entity of type ``T``: its analyzer creates it or finds an existing
    one, and the request sends it back to whoever yielded it.

    Every concrete request sets ``creates`` — ``T`` itself — in its own body, like
    ``axis``: a type parameter is gone at run time, so the engine checks what a request
    sends back against it.
    """

    creates: ClassVar[type[ScoreEntity]]


@abstract
@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteMutationRequest[T: ScoreEntity](MutationRequest):
    """A request that removes an existing ``target``."""

    target: T


@abstract
@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateMutationRequest[T: ScoreEntity](MutationRequest):
    """A request that mutates an existing ``target`` in place."""

    target: T
