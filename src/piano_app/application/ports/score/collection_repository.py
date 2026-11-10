from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True, kw_only=True)
class CollectionSummary:
    id: str
    name: str
    score_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class CollectionPin:
    """One collection item: the saved-score content version it holds, and whose collection it is."""

    item_id: str
    owner_id: str
    score_content_id: str


class CollectionRepository(Protocol):
    """Private, owner-only collections. An item pins the content version a score had when it was
    added. Whether the caller may touch a collection or a score was already settled by the caller;
    only ``get_owned`` and ``list_owned`` filter by owner."""

    async def create(self, *, owner_id: str, name: str) -> CollectionSummary: ...

    async def list_owned(self, *, owner_id: str) -> Sequence[CollectionSummary]: ...

    async def get_owned(self, *, collection_id: str, owner_id: str) -> CollectionSummary | None: ...

    async def rename(self, *, collection_id: str, name: str) -> None: ...

    async def delete(self, *, collection_id: str) -> None: ...

    async def add_score(self, *, collection_id: str, score_id: str, owner_id: str) -> bool:
        """Pins the score's current content version and returns ``True``, or returns ``False``
        when the owner cannot read the score. Readability is checked under a share lock on the
        score row, so a score cannot be hidden between the check and the pin. A score already in
        the collection, at any version, is left as it is."""
        ...

    async def remove_score(self, *, collection_id: str, score_id: str) -> None: ...

    async def collection_ids_with_score(self, *, owner_id: str, score_id: str) -> Sequence[str]: ...

    async def pins_of_other_owners(
        self, *, score_id: str, owner_id: str
    ) -> Sequence[CollectionPin]:
        """Every item of someone else's collection that pins any version of the score."""
        ...

    async def repin(self, *, item_id: str, score_id: str) -> None:
        """Re-points an item to the score's current content version."""
        ...
