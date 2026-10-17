from dataclasses import dataclass, field
from uuid import uuid4


@dataclass(slots=True, kw_only=True, eq=False)
class ScoreEntity:
    id: str = field(default_factory=lambda: uuid4().hex)

    # identity, not value equality -- two entities are the same iff they share an id,
    # never because their fields happen to match (matches the old dataclass eq=False)
    def __eq__(self, other: object) -> bool:
        return isinstance(other, ScoreEntity) and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

        object.__setattr__(self, name, value)

    # TODO remove from base
    def __post_init__(self) -> None:
        self._check_invariants()

    def _check_invariants(self) -> None:
        """Entity-local cross-field invariants, run after dataclass initialization."""
