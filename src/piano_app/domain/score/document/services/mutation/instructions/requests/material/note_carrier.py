from dataclasses import dataclass
from typing import ClassVar

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.models.notation import Articulation, Ornament
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceItem,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    Axis,
    CreateMutationRequest,
    UpdateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateNoteCarrierRequest(CreateMutationRequest[NoteCarrier]):
    """A request to create a note carrier on a given leaf or grace item."""

    axis: ClassVar[Axis | None] = Axis.CONTENT
    creates: ClassVar[type[ScoreEntity]] = NoteCarrier

    owner: LeafRhythmicContainer | GraceItem
    articulations: frozenset[Articulation] = frozenset()
    ornament: Ornament = Ornament.NONE


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateArticulationRequest(UpdateMutationRequest[NoteCarrier]):
    """A request to set the marks of articulation a note carrier has."""

    axis: ClassVar[Axis | None] = Axis.CONTENT

    articulations: frozenset[Articulation]


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateOrnamentRequest(UpdateMutationRequest[NoteCarrier]):
    """A request to set a note carrier's ornament."""

    axis: ClassVar[Axis | None] = Axis.CONTENT

    ornament: Ornament
