from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import DynamicMarking
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class SetDynamicIntent(EditIntent):
    """Set the dynamic of some voices from this place on."""

    measure_id: str
    position: MeasurePosition
    voice_ids: tuple[str, ...]
    dynamic: DynamicMarking


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateHairpinIntent(EditIntent):
    """Grow or fade between two places, to ``target``, for some voices that all start at
    the same dynamic."""

    start_measure_id: str
    start_position: MeasurePosition
    end_measure_id: str
    end_position: MeasurePosition
    voice_ids: tuple[str, ...]
    target: DynamicMarking


@dataclass(frozen=True, slots=True, kw_only=True)
class SetHairpinTargetIntent(EditIntent):
    """Change the dynamic an existing hairpin ends at."""

    hairpin_id: str
    target: DynamicMarking
