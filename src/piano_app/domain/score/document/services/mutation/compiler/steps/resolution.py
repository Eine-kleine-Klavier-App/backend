from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.services.indexing import EntityIndex
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError


def resolve_entities(
    *,
    entities: EntityIndex,
    entity_ids: Sequence[str],
) -> dict[str, ScoreEntity]:
    """The live entities behind the ids, keyed by id. An unknown id rejects the intent."""
    found: dict[str, ScoreEntity] = {}
    for entity_id in entity_ids:
        entity: ScoreEntity | None = entities.find(entity_id=entity_id)
        if entity is not None:
            found[entity_id] = entity

    unknown: set[str] = set(entity_ids) - found.keys()
    if unknown:
        raise MutationRejectedError(f"Could not resolve all ids: {unknown}")

    return found


def expect_entity[E: ScoreEntity](
    *,
    entities_by_id: dict[str, ScoreEntity],
    entity_id: str,
    expected: type[E],
) -> E:
    """The resolved entity narrowed to the type the intent requires, else a reject."""
    entity: ScoreEntity | None = entities_by_id.get(entity_id)
    if not isinstance(entity, expected):
        raise MutationRejectedError(
            f"Entity {entity_id!r} must be {expected.__name__}, "
            f"got {type(entity).__name__ if entity is not None else 'nothing'}."
        )

    return entity
