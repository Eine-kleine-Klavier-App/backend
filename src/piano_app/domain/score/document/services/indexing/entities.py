from collections.abc import Mapping
from types import MappingProxyType

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity

from .index import Index
from .ownership import owned_entities


class EntityIndex(Index):
    """Every entity of the document by its id, found at once.

    Built on its first read by following what each owner holds as its own, and kept right
    from then on: each link the journal reports being made or broken is counted, and an entity
    is in the index while some link of an owner that is in it holds it. An entity that comes
    with parts of its own brings them in, one that goes takes them with it. Unlike the other
    indexes it is not marked and healed on a read: counting a link costs next to nothing, and
    the parts of an entity are read at the moment the change leaves them.
    """

    def __init__(self, *, document: ScoreDocument) -> None:
        self._document: ScoreDocument = document
        self._links: dict[ScoreEntity, int] | None = None
        self._by_id: dict[str, ScoreEntity] = {}

    def find(self, *, entity_id: str) -> ScoreEntity | None:
        """The entity with this id, or ``None`` when the document holds none."""
        self._read()

        return self._by_id.get(entity_id)

    def held(self) -> Mapping[str, ScoreEntity]:
        """Every entity of the document by id."""
        self._read()

        return MappingProxyType(self._by_id)

    def attach_entity(self, *, owner: object, entity: ScoreEntity) -> None:
        if self._links is not None and self._is_held(owner=owner):
            self._hold(entity=entity)

    def detach_entity(self, *, owner: object, entity: ScoreEntity) -> None:
        if self._links is not None and self._is_held(owner=owner):
            self._release(entity=entity)

    def _read(self) -> None:
        if self._links is None:
            self._links = {}
            for entity in owned_entities(owner=self._document):
                self._hold(entity=entity)

    def _is_held(self, *, owner: object) -> bool:
        # a link of an owner outside the document counts for nothing: it was counted, if
        # at all, when the owner came in, and is let go with it
        return owner is self._document or (self._links is not None and owner in self._links)

    def _hold(self, *, entity: ScoreEntity) -> None:
        assert self._links is not None

        pending: list[ScoreEntity] = [entity]
        while pending:
            current: ScoreEntity = pending.pop()
            links: int = self._links.get(current, 0)
            self._links[current] = links + 1
            if links == 0:
                self._by_id[current.id] = current
                pending.extend(owned_entities(owner=current))

    def _release(self, *, entity: ScoreEntity) -> None:
        assert self._links is not None

        pending: list[ScoreEntity] = [entity]
        while pending:
            current: ScoreEntity = pending.pop()
            links: int | None = self._links.get(current)
            if links is None:
                continue

            if links > 1:
                self._links[current] = links - 1
                continue

            del self._links[current]
            del self._by_id[current.id]
            pending.extend(owned_entities(owner=current))
