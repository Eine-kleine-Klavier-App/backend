from collections.abc import Sequence
from typing import Any

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.context import (
    ClefChange,
    Context,
    OctaveTransposition,
)
from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.structural import (
    Measure,
    Staff,
    TemporalAnchor,
    Voice,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
    RhythmicContainerParent,
)

from .index import Index
from .ownership import owns

_ANCHOR_PLACE_FIELDS: tuple[str, ...] = ("_measure", "_position")
_ANCHOR_CONTEXT_FIELDS: tuple[str, ...] = ("_starting_contexts", "_ending_contexts")
# a container's size, or the group it sits under, decides how long it lasts on the timeline
_CONTAINER_FIELDS: tuple[str, ...] = ("written_size", "occupied_size", "_parent")
_CONTEXT_EDGE_FIELDS: tuple[str, ...] = ("_start", "_end")
# where a note stands on its staff and its sign decide which accidental is in force after it
_NOTE_FIELDS: tuple[str, ...] = ("_staff", "_staff_step", "_accidental")


class IndexLayer(Index):
    """Tells the indexes what the journal has just changed.

    The indexes are told in the order they are given: one that reads another comes after it.
    A rule names the type of the owner and the field and says what the change means; a change
    no rule names touches no index. The rules mark what went stale and the next read rebuilds
    it, so a change in the middle of a larger edit never builds from a half-changed model.
    The layer is itself an index: each event goes to every index it holds.
    """

    def __init__(self, *, indexes: Sequence[Index]) -> None:
        self._indexes: tuple[Index, ...] = tuple(indexes)

    def invalidate_measures(self) -> None:
        for index in self._indexes:
            index.invalidate_measures()

    def invalidate_anchor(self, *, anchor: TemporalAnchor) -> None:
        for index in self._indexes:
            index.invalidate_anchor(anchor=anchor)

    def invalidate_leaf(self, *, leaf: LeafRhythmicContainer) -> None:
        for index in self._indexes:
            index.invalidate_leaf(leaf=leaf)

    def invalidate_group(self, *, group: GroupRhythmicContainer) -> None:
        for index in self._indexes:
            index.invalidate_group(group=group)

    def invalidate_child(self, *, scope: RhythmicContainerParent, child: RhythmicContainer) -> None:
        for index in self._indexes:
            index.invalidate_child(scope=scope, child=child)

    def invalidate_staff(self, *, staff: Staff) -> None:
        for index in self._indexes:
            index.invalidate_staff(staff=staff)

    def invalidate_context(self, *, context: Context) -> None:
        for index in self._indexes:
            index.invalidate_context(context=context)

    def invalidate_note(self, *, note: Note) -> None:
        for index in self._indexes:
            index.invalidate_note(note=note)

    def attach_entity(self, *, owner: object, entity: ScoreEntity) -> None:
        for index in self._indexes:
            index.attach_entity(owner=owner, entity=entity)

    def detach_entity(self, *, owner: object, entity: ScoreEntity) -> None:
        for index in self._indexes:
            index.detach_entity(owner=owner, entity=entity)

    def on_set(self, target: object, field_name: str, previous: object) -> None:
        if owns(owner=target, field_name=field_name):
            if isinstance(previous, ScoreEntity):
                self.detach_entity(owner=target, entity=previous)

            current: object = getattr(target, field_name)
            if isinstance(current, ScoreEntity):
                self.attach_entity(owner=target, entity=current)

        if isinstance(target, Measure) and field_name == "_time_signature":
            self.invalidate_measures()
        elif isinstance(target, TemporalAnchor) and field_name in _ANCHOR_PLACE_FIELDS:
            self.invalidate_anchor(anchor=target)
        elif isinstance(target, LeafRhythmicContainer) and field_name in _CONTAINER_FIELDS:
            self.invalidate_leaf(leaf=target)
        elif isinstance(target, GroupRhythmicContainer) and field_name in _CONTAINER_FIELDS:
            self.invalidate_group(group=target)
        elif isinstance(target, Context) and field_name in _CONTEXT_EDGE_FIELDS:
            self.invalidate_context(context=target)
            if isinstance(target, ClefChange | OctaveTransposition):
                self.invalidate_staff(staff=target.staff)
        elif isinstance(target, Note) and field_name in _NOTE_FIELDS:
            self.invalidate_note(note=target)

    def on_list(self, owner: object, field_name: str, item: Any, added: bool) -> None:
        if isinstance(item, ScoreEntity) and owns(owner=owner, field_name=field_name):
            if added:
                self.attach_entity(owner=owner, entity=item)
            else:
                self.detach_entity(owner=owner, entity=item)

        if isinstance(owner, ScoreDocument) and field_name == "_measures":
            self.invalidate_measures()
        elif (
            isinstance(owner, Voice | GroupRhythmicContainer)
            and field_name == "_children"
            and isinstance(item, RhythmicContainer)
        ):
            self.invalidate_child(scope=owner, child=item)
        elif isinstance(owner, NoteCarrier) and field_name == "_notes" and isinstance(item, Note):
            self.invalidate_note(note=item)
        elif isinstance(owner, Staff) and field_name == "_contexts":
            self.invalidate_staff(staff=owner)
        elif (
            isinstance(owner, TemporalAnchor)
            and field_name in _ANCHOR_CONTEXT_FIELDS
            and isinstance(item, Context)
        ):
            self.invalidate_context(context=item)
            if isinstance(item, ClefChange | OctaveTransposition):
                self.invalidate_staff(staff=item.staff)
