from collections.abc import Iterator

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.material import (
    Carrier,
    Note,
    NoteCarrier,
    RestCarrier,
)
from piano_app.domain.score.document.models.structural import Measure, TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.models.structural.rhythm.grace import GraceGroup, GraceItem

# What each kind of owner holds as its own, by field: the one place that says which links of
# the model carry ownership and which only point back or sideways. An entity is in the document
# as long as an owner that is in it holds it. A rhythmic container is held by its anchor (a
# voice or a group lists it too, as a mirror), a note by its carrier (its staff lists it too),
# a context by the anchor it starts on (the staffs, voices and an end anchor list it too).
_OWNED_FIELDS: tuple[tuple[type, tuple[str, ...]], ...] = (
    (ScoreDocument, ("_voices", "_staffs", "_measures")),
    (Measure, ("_anchors",)),
    (
        TemporalAnchor,
        ("_containers", "_starting_contexts", "_departing_jumps", "_arriving_jumps"),
    ),
    (LeafRhythmicContainer, ("_carrier", "_grace_before", "_grace_after")),
    (GraceGroup, ("_grace_items",)),
    (GraceItem, ("_carrier",)),
    (Carrier, ("_carrier_group_relations",)),
    (NoteCarrier, ("_notes",)),
    (RestCarrier, ("_rest",)),
    (Note, ("_relations",)),
)


_BY_KIND: dict[type, tuple[str, ...]] = {}


def _owned_fields(kind: type) -> tuple[str, ...]:
    fields: tuple[str, ...] | None = _BY_KIND.get(kind)
    if fields is None:
        fields = tuple(
            field_name
            for owner, field_names in _OWNED_FIELDS
            if issubclass(kind, owner)
            for field_name in field_names
        )
        _BY_KIND[kind] = fields

    return fields


def owns(*, owner: object, field_name: str) -> bool:
    """Whether a link from ``owner`` through ``field_name`` makes its target part of the
    document while the owner is."""
    return field_name in _owned_fields(type(owner))


def owned_entities(*, owner: ScoreEntity | ScoreDocument) -> Iterator[ScoreEntity]:
    """What the owner holds as its own, once for each link."""
    for field_name in _owned_fields(type(owner)):
        value: object = getattr(owner, field_name)
        if isinstance(value, ScoreEntity):
            yield value
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, ScoreEntity):
                    yield item
