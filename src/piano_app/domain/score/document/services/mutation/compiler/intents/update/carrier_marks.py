from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import Articulation, Ornament
from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class CarrierMarks:
    """The marks one note carrier is given; a mark left as ``None`` is not touched."""

    carrier_id: str
    articulations: frozenset[Articulation] | None = None
    ornament: Ornament | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class SetCarrierMarksIntent(EditIntent):
    """Give the marks of articulation and ornament to several note carriers in one gesture, so
    one undo takes them all back."""

    items: tuple[CarrierMarks, ...]
