from dataclasses import dataclass

from piano_app.domain.score.document.services.mutation.compiler.base import EditIntent


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateBeamIntent(EditIntent):
    """Beam these carriers together, given in time order — a beam's members are its timeline
    order, so a selection in any other order is refused, not sorted."""

    carrier_ids: tuple[str, ...]
