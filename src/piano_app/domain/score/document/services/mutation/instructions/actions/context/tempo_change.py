from dataclasses import dataclass

from piano_app.domain.score.document.models.context import TempoChange
from piano_app.domain.score.document.models.notation import DottedRhythmicValue
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.services.mutation.instructions.actions.base import (
    CreateMutationAction,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateTempoChangeAction(CreateMutationAction[TempoChange]):
    """Creates a tempo change on its anchor."""

    start: TemporalAnchor
    beat: DottedRhythmicValue
    bpm: int
    show_label: bool
