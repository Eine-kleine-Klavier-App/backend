from dataclasses import dataclass

from piano_app.domain.score.document.models.material import Carrier
from piano_app.domain.score.document.models.relations import Beam
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    CreateMutationAction,
    UpdateMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateBeamMembersAction(UpdateMutationAction[Beam]):
    """Keeps a beam on a run of its consecutive members only."""

    carriers: tuple[Carrier, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class AddBeamMemberAction(UpdateMutationAction[Beam]):
    """Takes a carrier into a beam, right after one of its members."""

    carrier: Carrier
    after: Carrier


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateBeamAction(CreateMutationAction[Beam]):
    """Creates a beam over carriers."""

    carriers: tuple[Carrier, ...]
