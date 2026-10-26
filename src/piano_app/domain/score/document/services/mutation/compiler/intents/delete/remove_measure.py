from dataclasses import dataclass

from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class RemoveMeasureIntent(EditIntent):
    """Remove this measure with everything inside it; the last remaining measure stays."""

    measure_id: str
