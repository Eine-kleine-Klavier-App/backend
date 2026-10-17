from dataclasses import dataclass

from piano_app.domain.score.document.models.notation import StemOverride
from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class SetStemIntent(EditIntent):
    """Draw the stems of these note carriers the same way — one carrier dragged, or a
    whole selection set at once — as one gesture."""

    carrier_ids: tuple[str, ...]
    override: StemOverride


@dataclass(frozen=True, slots=True, kw_only=True)
class ResetStemIntent(EditIntent):
    """Draw the stems of these note carriers automatically again, as one gesture."""

    carrier_ids: tuple[str, ...]
