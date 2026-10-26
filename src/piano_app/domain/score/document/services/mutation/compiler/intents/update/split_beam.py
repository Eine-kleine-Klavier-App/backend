from dataclasses import dataclass

from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class SplitBeamIntent(EditIntent):
    """Break a beam before one of its carriers without changing its material."""

    beam_id: str
    before_carrier_id: str
