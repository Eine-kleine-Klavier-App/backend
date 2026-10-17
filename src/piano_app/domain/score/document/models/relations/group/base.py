from collections.abc import Sequence
from dataclasses import dataclass

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.relations.base import Relation
from piano_app.domain.shared.abstract import abstract


@abstract
@dataclass(slots=True, kw_only=True, eq=False)
class GroupRelation[T: ScoreEntity](Relation):
    _members: list[T]

    @property
    def members(self) -> Sequence[T]:
        return self._members

    def __post_init__(self) -> None:
        super().__post_init__()
        self._check_members()

    def _check_members(self) -> None:
        if not self._members:
            raise ValueError("Group relation must contain at least one member.")

        if len(self._members) != len(set(self._members)):
            raise ValueError("Group relation members must be unique.")
