from dataclasses import dataclass

from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class VoltaFragmentIntent:
    """One fragment of a volta: where it ends (no end: it lasts until the end of the score)
    and the passes it is played in. It starts where the one before it ends."""

    end_measure_id: str | None
    end_position: MeasurePosition | None
    passes: tuple[int, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateVoltaIntent(EditIntent):
    """Make the endings of a repeat: a body that every pass plays, from where it starts to
    where it ends, and fragments that follow, each played in its own passes."""

    start_measure_id: str
    start_position: MeasurePosition
    body_end_measure_id: str
    body_end_position: MeasurePosition
    fragments: tuple[VoltaFragmentIntent, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class MoveVoltaBoundaryIntent(EditIntent):
    """Drag a boundary of a volta to another place. Boundary 0 is where the body ends,
    boundary ``i`` where fragment ``i`` ends; without a place it is the end of the score."""

    volta_id: str
    boundary: int
    measure_id: str | None
    position: MeasurePosition | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MoveVoltaStartIntent(EditIntent):
    """Move the place the body of a volta starts at; only the body changes."""

    volta_id: str
    measure_id: str
    position: MeasurePosition


@dataclass(frozen=True, slots=True, kw_only=True)
class SetVoltaFragmentPassesIntent(EditIntent):
    """Set the passes a fragment of a volta is played in; ``fragment`` is counted from zero and
    is not the first, which is played in the passes the others leave."""

    volta_id: str
    fragment: int
    passes: tuple[int, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class SetVoltaTimesIntent(EditIntent):
    """Set how many times a volta is played; the first fragment takes every pass before the
    last that the others do not hold."""

    volta_id: str
    times: int


@dataclass(frozen=True, slots=True, kw_only=True)
class AppendVoltaFragmentIntent(EditIntent):
    """Add a fragment after the last one of a volta, ending at the given place (none: the end
    of the score)."""

    volta_id: str
    measure_id: str | None
    position: MeasurePosition | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SplitVoltaFragmentIntent(EditIntent):
    """Cut the last fragment of a volta at the given place."""

    volta_id: str
    measure_id: str
    position: MeasurePosition


@dataclass(frozen=True, slots=True, kw_only=True)
class AddRefrainEndingIntent(EditIntent):
    """Make the first ending of a repeat: the repeat becomes a volta whose body is the stretch it
    played and whose first ending ends at the given place (none: the end of the score). The ending
    is played in every pass but the last, so the repeat is played as many times as before."""

    refrain_id: str
    measure_id: str | None
    position: MeasurePosition | None
