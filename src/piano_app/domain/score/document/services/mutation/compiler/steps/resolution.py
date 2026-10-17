import dataclasses
from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError


def resolve_entities(
    *,
    document: ScoreDocument,
    entity_ids: Sequence[str],
) -> dict[str, ScoreEntity]:
    """The live entities behind the ids, keyed by id. An unknown id rejects the intent."""
    ids: set[str] = set(entity_ids)
    found: dict[str, ScoreEntity] = {}
    seen: set[str] = set()
    stack: list[ScoreEntity] = []

    def schedule_children_of(parent: ScoreEntity | ScoreDocument) -> None:
        for field in dataclasses.fields(parent):
            for child_entity in _flatten(getattr(parent, field.name)):
                if child_entity.id not in seen:
                    seen.add(child_entity.id)
                    stack.append(child_entity)

    schedule_children_of(document)

    while stack:
        entity: ScoreEntity = stack.pop()

        # register matching entities
        if entity.id in ids:
            found[entity.id] = entity

            # tiny optimization here, stop if all ids were found
            if len(found) == len(ids):
                break

        # keep searching deeper for children
        schedule_children_of(entity)

    if len(found) != len(ids):
        raise MutationRejectedError(f"Could not resolve all ids: {ids - found.keys()}")

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


def _flatten(value: object) -> list[ScoreEntity]:
    """Flatten a field value to the entities it holds, recursing through the standard
    containers (list/tuple/set/dict). A ``ScoreEntity`` is terminal.
    """
    entities: list[ScoreEntity] = []
    if isinstance(value, ScoreEntity):
        entities.append(value)
    elif isinstance(value, list | tuple | set):
        for item in value:
            entities.extend(_flatten(item))
    elif isinstance(value, dict):
        for item in value.values():
            entities.extend(_flatten(item))

    return entities
