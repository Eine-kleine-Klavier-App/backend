from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import Articulation
from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class SetArticulationIntent(EditIntent):
    """Give this note carrier exactly these marks of articulation; an empty set clears them. A
    set that holds an exclusive pair is refused."""

    carrier_id: str
    articulations: frozenset[Articulation]


@dataclass(frozen=True, slots=True, kw_only=True)
class ToggleArticulationIntent(EditIntent):
    """Take this mark off the note carrier if it has it, else put it on, replacing the marks
    it excludes."""

    carrier_id: str
    articulation: Articulation
