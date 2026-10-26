from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import Ornament
from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class SetOrnamentIntent(EditIntent):
    """Mark this note carrier with an ornament; ``Ornament.NONE`` clears it."""

    carrier_id: str
    ornament: Ornament
