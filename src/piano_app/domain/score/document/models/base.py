from dataclasses import dataclass, field
from uuid import uuid4


@dataclass(slots=True, kw_only=True, eq=False)
class ScoreEntity:
    id: str = field(default_factory=lambda: uuid4().hex)

    # TODO remove from base
    def __post_init__(self) -> None:
        self._check_invariants()

    def _check_invariants(self) -> None:
        """Entity-local cross-field invariants, run after dataclass initialization."""
