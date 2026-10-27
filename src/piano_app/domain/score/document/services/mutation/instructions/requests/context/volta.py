from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.context import Volta
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
    UpdateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class VoltaFragmentRequest:
    """One fragment of a volta: the measure and position it ends at (neither: it lasts until
    the end of the score) and the passes it is played in."""

    end_measure: Measure | None
    end_position: MeasurePosition | None
    passes: frozenset[int]


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateVoltaRequest(CreateMutationRequest[Volta]):
    """A request to assert the endings of a repeat: a body from where it starts to where it
    ends and the fragments that follow it, each in its own passes."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS
    creates: ClassVar[type[ScoreEntity]] = Volta

    start_measure: Measure
    start_position: MeasurePosition
    body_end_measure: Measure
    body_end_position: MeasurePosition
    fragments: tuple[VoltaFragmentRequest, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class MoveVoltaBoundaryRequest(UpdateMutationRequest[Volta]):
    """A request to drag a boundary of a volta to another place, keeping the volta. No measure
    means the end of the score."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS

    boundary: int
    measure: Measure | None
    position: MeasurePosition | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MoveVoltaStartRequest(UpdateMutationRequest[Volta]):
    """A request to move the place the body of a volta starts at, keeping the volta."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS

    measure: Measure
    position: MeasurePosition


@dataclass(frozen=True, slots=True, kw_only=True)
class SetVoltaFragmentPassesRequest(UpdateMutationRequest[Volta]):
    """A request to set the passes a fragment of a volta is played in, keeping the volta."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS

    fragment: int
    passes: frozenset[int]


@dataclass(frozen=True, slots=True, kw_only=True)
class SetVoltaTimesRequest(UpdateMutationRequest[Volta]):
    """A request to set how many times a volta is played, keeping the volta."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS

    times: int


@dataclass(frozen=True, slots=True, kw_only=True)
class AppendVoltaFragmentRequest(UpdateMutationRequest[Volta]):
    """A request to add a fragment after the last one of a volta, ending at the place; no
    measure means the end of the score."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS

    measure: Measure | None
    position: MeasurePosition | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SplitVoltaFragmentRequest(UpdateMutationRequest[Volta]):
    """A request to cut the last fragment of a volta at the place."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS

    measure: Measure
    position: MeasurePosition


@dataclass(frozen=True, slots=True, kw_only=True)
class CollapseVoltaRequest(UpdateMutationRequest[Volta]):
    """A request to draw the boundaries of a volta that lie in a measure about to be removed
    to where the measure ends; a fragment left with no length goes with its passes, a volta
    left with no body or no fragment is deleted."""

    axis: ClassVar[Axis | None] = Axis.CONTEXTS

    measure: Measure
