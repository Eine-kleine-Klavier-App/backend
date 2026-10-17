from dataclasses import dataclass

from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.models.notation import (
    Articulation,
    DottedRhythmicValue,
    StemOverride,
)
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition
from piano_app.domain.score.document.models.structural.rhythm import RhythmicContainerParent
from piano_app.domain.score.document.services.mutation.instructions.refs import Bound
from piano_app.domain.score.document.services.mutation.instructions.requests.base import (
    CreateMutationRequest,
    DeleteMutationRequest,
    UpdateMutationRequest,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateNoteCarrierRequest(CreateMutationRequest[NoteCarrier]):
    """A request to create a note carrier in a rhythmic scope at a measure position."""

    scope: Bound[RhythmicContainerParent]
    measure: Measure

    position: MeasurePosition
    written_value: DottedRhythmicValue
    articulation: Articulation = Articulation.NONE


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteNoteCarrierRequest(DeleteMutationRequest[NoteCarrier]):
    """A request to delete a note carrier."""


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateStemRequest(UpdateMutationRequest[NoteCarrier]):
    """A request to draw a note carrier's stem as given; ``None`` draws it automatically."""

    stem: StemOverride | None
