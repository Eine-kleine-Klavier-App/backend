from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import DottedRhythmicValue, TempoMarking
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class SetTempoIntent(EditIntent):
    """Set the tempo of the score from this place on: a number of beats of ``beat`` per
    minute, a word, or both. A word alone gets the middle of its usual range, in quarter notes;
    a number needs its beat."""

    measure_id: str
    position: MeasurePosition
    beat: DottedRhythmicValue | None = None
    bpm: int | None = None
    show_label: bool = False
    label: TempoMarking | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateTempoTransitionIntent(EditIntent):
    """Speed up or slow down between two places, to ``target_bpm`` beats per minute of the
    beat of the tempo in force at the start."""

    start_measure_id: str
    start_position: MeasurePosition
    end_measure_id: str
    end_position: MeasurePosition
    target_bpm: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SetTempoTransitionTargetIntent(EditIntent):
    """Change the tempo an existing tempo transition ends at."""

    transition_id: str
    target_bpm: int
