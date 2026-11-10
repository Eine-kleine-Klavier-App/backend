from piano_app.application.errors import CollectionNotFoundError
from piano_app.application.ports import CollectionRepository, CollectionSummary


async def require_owned_collection(
    *,
    collection_repository: CollectionRepository,
    collection_id: str,
    owner_id: str,
) -> CollectionSummary:
    collection: CollectionSummary | None = await collection_repository.get_owned(
        collection_id=collection_id, owner_id=owner_id
    )
    if collection is None:
        raise CollectionNotFoundError(collection_id=collection_id)

    return collection
