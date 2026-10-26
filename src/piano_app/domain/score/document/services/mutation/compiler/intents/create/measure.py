from dataclasses import dataclass

from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class AppendMeasureIntent(EditIntent):
    """Add a measure after the last one, with the last measure's time signature."""


@dataclass(frozen=True, slots=True, kw_only=True)
class InsertMeasureIntent(EditIntent):
    """Add a measure right before this one, with its left neighbour's time signature — or
    this measure's own when it is the first."""

    before_measure_id: str
