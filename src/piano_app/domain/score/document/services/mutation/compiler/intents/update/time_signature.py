from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import RhythmicSize
from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeTimeSignatureIntent(EditIntent):
    """Give exactly these measures — contiguous — this time signature; everything in them
    keeps its time from their start and only the barlines move."""

    measure_ids: tuple[str, ...]
    time_signature: RhythmicSize
