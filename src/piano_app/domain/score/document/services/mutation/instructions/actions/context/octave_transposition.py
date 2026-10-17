from dataclasses import dataclass

from piano_app.domain.score.document.models.context import OctaveTransposition
from piano_app.domain.score.document.models.structural import Staff, TemporalAnchor
from piano_app.domain.score.document.services.mutation.instructions import Bound
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    CreateMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateOctaveTranspositionAction(CreateMutationAction[OctaveTransposition]):
    """Creates an octave transposition on its anchors."""

    start: Bound[TemporalAnchor]
    end: Bound[TemporalAnchor]
    staff: Staff
    octaves: int
