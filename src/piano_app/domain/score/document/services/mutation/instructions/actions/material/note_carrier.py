from dataclasses import dataclass

from piano_app.domain.score.document.models.material import CarrierOwner, NoteCarrier
from piano_app.domain.score.document.models.notation import Articulation, Ornament
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    CreateMutationAction,
    DeleteMutationAction,
    UpdateMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateNoteCarrierAction(CreateMutationAction[NoteCarrier]):
    """Creates a note carrier owned by a leaf or grace item."""

    owner: CarrierOwner
    articulations: frozenset[Articulation] = frozenset()
    ornament: Ornament = Ornament.NONE


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteNoteCarrierAction(DeleteMutationAction[NoteCarrier]):
    """Deletes a note carrier."""


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateArticulationAction(UpdateMutationAction[NoteCarrier]):
    """Sets the marks of articulation a note carrier has."""

    articulations: frozenset[Articulation]


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateOrnamentAction(UpdateMutationAction[NoteCarrier]):
    """Sets a note carrier's ornament."""

    ornament: Ornament
