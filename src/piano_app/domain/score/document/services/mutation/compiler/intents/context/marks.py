from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import Accidental, Clef
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent

from .mode import PitchEditMode


@dataclass(frozen=True, slots=True, kw_only=True)
class SetKeySignatureIntent(EditIntent):
    """Set the key signature of a staff from this place on: the accidental of each of the seven
    diatonic steps, C to B."""

    staff_id: str
    measure_id: str
    position: MeasurePosition
    alterations: tuple[Accidental, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateSlurIntent(EditIntent):
    start_measure_id: str
    start_position: MeasurePosition
    end_measure_id: str
    end_position: MeasurePosition
    voice_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateSustainHoldIntent(EditIntent):
    """Hold the damper pedal from one place to another, for the whole score."""

    start_measure_id: str
    start_position: MeasurePosition
    end_measure_id: str
    end_position: MeasurePosition


@dataclass(frozen=True, slots=True, kw_only=True)
class SetClefIntent(EditIntent):
    """Set the clef of a staff from this place on, and with it what its notes sound like or
    where they stand, as ``mode`` says."""

    staff_id: str
    measure_id: str
    position: MeasurePosition
    clef: Clef
    octave_transposition: int
    mode: PitchEditMode


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateOctaveTranspositionIntent(EditIntent):
    """Play a stretch of a staff some octaves higher or lower than written; ``mode`` says
    whether its notes then move to sound as before or stay put and sound different."""

    staff_id: str
    start_measure_id: str
    start_position: MeasurePosition
    end_measure_id: str
    end_position: MeasurePosition
    octaves: int
    mode: PitchEditMode


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteClefIntent(EditIntent):
    """Take a clef out of some measures: the clef before it governs them, and it returns at the
    start of the measure after the last one chosen, unless another clef starts there or its
    stretch ended already. The measures are contiguous and hold the clef; none given means the
    measure the clef stands in. The notes it reached move or stay as ``mode`` says."""

    clef_id: str
    measure_ids: tuple[str, ...]
    mode: PitchEditMode


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteOctaveTranspositionIntent(EditIntent):
    """Delete an octave line, the notes it reached moving or staying as ``mode`` says."""

    octave_id: str
    mode: PitchEditMode


@dataclass(frozen=True, slots=True, kw_only=True)
class MoveContextStartIntent(EditIntent):
    """Move where a context starts; ``mode`` matters only for a clef or an octave line."""

    context_id: str
    measure_id: str
    position: MeasurePosition
    mode: PitchEditMode


@dataclass(frozen=True, slots=True, kw_only=True)
class MoveContextEndIntent(EditIntent):
    """Move where a span context ends; ``mode`` matters only for an octave line."""

    context_id: str
    measure_id: str
    position: MeasurePosition
    mode: PitchEditMode


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenContextEndIntent(EditIntent):
    """Make a span context last until the end of the score; ``mode`` matters only for an
    octave line."""

    context_id: str
    mode: PitchEditMode
