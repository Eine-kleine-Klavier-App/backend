from dataclasses import dataclass

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.relations.base import Relation
from piano_app.domain.shared.abstract import abstract


@abstract
@dataclass(slots=True, kw_only=True, eq=False)
class StartEndRelation[T: ScoreEntity](Relation):
    _start: T
    _end: T

    @property
    def start(self) -> T:
        return self._start

    @property
    def end(self) -> T:
        return self._end

    def _check_invariants(self) -> None:
        super()._check_invariants()

        if self._start is self._end:
            raise ValueError("Start and end must be different entities.")
