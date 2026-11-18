from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.material import Carrier
from piano_app.domain.score.document.models.relations import Beam
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
    UpdateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateBeamMembersRequest(UpdateMutationRequest[Beam]):
    """A request to keep a beam on ``carriers`` only, a run of its consecutive members."""

    axis: ClassVar[Axis | None] = Axis.RELATIONS

    carriers: tuple[Carrier, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class AddBeamMemberRequest(UpdateMutationRequest[Beam]):
    """A request to take ``carrier`` into a beam, right after its member ``after``."""

    axis: ClassVar[Axis | None] = Axis.RELATIONS

    carrier: Carrier
    after: Carrier


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateBeamRequest(CreateMutationRequest[Beam]):
    """A request to beam ``carriers`` together."""

    axis: ClassVar[Axis | None] = Axis.RELATIONS
    creates: ClassVar[type[ScoreEntity]] = Beam

    carriers: tuple[Carrier, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class SplitBeamRequest(UpdateMutationRequest[Beam]):
    """Break the relation before a member, keeping runs of at least two."""

    axis: ClassVar[Axis | None] = Axis.RELATIONS

    before_carrier: Carrier
