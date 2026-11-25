from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import DynamicMarking
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class SetDynamicIntent(EditIntent):
    """Set the dynamic of some voices from this place on: one dynamic for each voice."""

    measure_id: str
    position: MeasurePosition
    voice_ids: tuple[str, ...]
    dynamic: DynamicMarking


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateHairpinIntent(EditIntent):
    """Grow or fade between two places, to ``target``, for some voices: one hairpin for each
    voice, each counting its levels from the dynamic its voice is at."""

    start_measure_id: str
    start_position: MeasurePosition
    end_measure_id: str
    end_position: MeasurePosition
    voice_ids: tuple[str, ...]
    target: DynamicMarking


@dataclass(frozen=True, slots=True, kw_only=True)
class SetHairpinTargetIntent(EditIntent):
    """Change the dynamic existing hairpins end at."""

    hairpin_ids: tuple[str, ...]
    target: DynamicMarking
