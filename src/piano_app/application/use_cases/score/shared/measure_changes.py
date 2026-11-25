"""Which measures an edit changed, read from the change of the record the edit made.

Each row the change names belongs to the measure its entity is kept with when the view is cut by
measure (see ``ScoreView``): a row that is there after the edit is found in the view of the score
after it, a row that is gone is found in the rows of the record before it. Some rows reach further
than their measure: a key, a clef or an octave line changes what the notes after it sound until
the next one on its staff, a dynamic or a hairpin the loudness of its voice until its next
dynamic, a tie or a glissando both of its notes, and a change of tempo, of the pedal, of the
order of play or of the measures themselves the time of everything that follows. What cannot be
placed is taken as a change of every measure.
"""

import json
from dataclasses import dataclass
from typing import Any

from piano_app.application.ports.score import DocumentRecord, RecordChange
from piano_app.domain.score.document import ScoreDocument
from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.context import (
    ClefChange,
    Context,
    DynamicChange,
    Hairpin,
    KeySignatureChange,
    OctaveTransposition,
    SpanContext,
    StaffScoped,
    TempoTransition,
    VoiceScoped,
)
from piano_app.domain.score.document.models.material.primitive import Note
from piano_app.domain.score.document.models.relations import Glissando, Tie
from piano_app.domain.score.document.services.indexing import EntityIndex

from .view import ScoreView

# the contexts whose change reaches what the notes after them sound, until the next one of the
# same kind on their staff
_PITCH_KINDS: dict[str, type[Context]] = {
    "key_signature_change": KeySignatureChange,
    "clef_change": ClefChange,
    "octave_transposition": OctaveTransposition,
}
# the contexts whose change reaches the loudness of their voice until its next dynamic
_LOUDNESS_KINDS: frozenset[str] = frozenset({"dynamic_change", "hairpin"})
# the contexts whose change moves the time of what follows; the view shows the tempo a
# transition goes from and to
_TEMPO_KINDS: frozenset[str] = frozenset({"tempo_change", "tempo_transition"})
# the contexts that are only drawn
_DRAWN_KINDS: frozenset[str] = frozenset({"slur"})
# the tables whose rows are entities the view keeps with a measure, in the order they are looked in
_ENTITY_TABLES: tuple[str, ...] = (
    "rhythmic",
    "grace_groups",
    "grace_items",
    "carriers",
    "musical_items",
    "relations",
    "contexts",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasureChanges:
    """What an edit changed, by the id of the measure: the share of the view a client draws and
    the sound. None is every measure. ``header``: what belongs to no one measure changed."""

    content: frozenset[str] | None
    sound: frozenset[str] | None
    header: bool


def measure_changes(
    *,
    before: DocumentRecord,
    change: RecordChange,
    document: ScoreDocument,
    view: ScoreView,
) -> MeasureChanges:
    """The measures ``change`` reached. ``before`` is the record it was made from, ``document``
    the score after it and ``view`` the view of that score."""
    reach: _Reach = _Reach(before=before, document=document, view=view)

    for name, field_change in change.get("fields", {}).items():
        reach.read_field(name=name, field_change=field_change)

    for table, rows in change.get("tables", {}).items():
        for row_id, pair in rows.items():
            reach.read_row(table=table, row_id=row_id, old=pair[0], new=pair[1])

    return reach.result()


class _Reach:
    """The measures a change reaches, gathered row by row."""

    def __init__(self, *, before: DocumentRecord, document: ScoreDocument, view: ScoreView) -> None:
        self._before: _RecordHomes = _RecordHomes(record=before)
        self._document: ScoreDocument = document
        self._view: ScoreView = view
        self._measure_ids: list[str] = [measure.id for measure in document.measures]
        self._order: dict[str, int] = {
            measure_id: index for index, measure_id in enumerate(self._measure_ids)
        }
        self._content: set[str] = set()
        self._sound: set[str] = set()
        self._every_content: bool = False
        self._every_sound: bool = False
        self._header: bool = False
        # the contexts of the score after the edit in the order they start, and its entities by
        # id, read the first time a rule needs them
        self._contexts: list[Context] | None = None
        self._entities: EntityIndex | None = None

    def result(self) -> MeasureChanges:
        return MeasureChanges(
            content=None if self._every_content else frozenset(self._content),
            sound=None if self._every_sound else frozenset(self._sound | self._content),
            header=self._header,
        )

    def read_field(self, *, name: str, field_change: Any) -> None:
        if name == "music_revision":
            self._header = True
        elif name == "relation_ids":
            # every relation that came or went has its row in the change
            return
        elif name == "measure_ids" and isinstance(field_change, dict):
            # a measure that came is drawn; everything after one that came or went sounds at
            # another time
            self._header = True
            self._every_sound = True
            for _, measure_id in field_change.get("inserted", []):
                self._content.add(str(measure_id))
        elif name == "presentation" and isinstance(field_change, list):
            self._read_placements(old=field_change[0] or {}, new=field_change[1] or {})
        else:
            self._header = True
            self._every_content = True
            self._every_sound = True

    def read_row(self, *, table: str, row_id: str, old: Any, new: Any) -> None:
        home_after: str | None = None
        if new is not None:
            home_after = self._home_after(table=table, row_id=row_id, row=new)
            self._add_home(home=home_after)

        home_before: str | None = None
        if old is not None:
            home_before = self._before.home(table=table, row_id=row_id)
            self._add_home(home=home_before)

        if table == "measures":
            # a time signature moves the time of everything after its measure
            self._every_sound = True
        elif table == "contexts":
            if old is not None:
                self._read_context(row=old, home=home_before, end_after=False)
            if new is not None:
                self._read_context(row=new, home=home_after, end_after=True)
        elif table == "relations":
            for row in (old, new):
                if row is not None and row.get("kind") in ("tie", "glissando"):
                    for note_id in (row["start_note_id"], row["end_note_id"]):
                        self._add_home(home=self._home_of_any(entity_id=str(note_id)))
        elif table == "musical_items" and new is not None:
            self._read_note(note_id=row_id)

    def _home_after(self, *, table: str, row_id: str, row: Any) -> str | None:
        if table == "measures":
            return row_id

        if table == "anchors":
            return str(row["measure_id"])

        return self._view.home_of(entity_id=row_id)

    def _home_of_any(self, *, entity_id: str) -> str | None:
        """Where an entity is kept after the edit, or where it was before it if it is gone."""
        home: str | None = self._view.home_of(entity_id=entity_id)
        return home if home is not None else self._before.home_of_entity(entity_id=entity_id)

    def _add_home(self, *, home: str | None) -> None:
        if home is None:
            self._every_content = True
            self._every_sound = True
        else:
            self._content.add(home)

    def _read_context(self, *, row: Any, home: str | None, end_after: bool) -> None:
        if home is None:
            return

        kind: object = row.get("kind")
        if kind in _PITCH_KINDS:
            # the notes after it sound otherwise, in the view (their MIDI number) and in the sound
            staff_id: object = row.get("staff_id")
            until: int | None = self._next_measure(
                start=home,
                matches=lambda context: (
                    isinstance(context, _PITCH_KINDS[str(kind)])
                    and isinstance(context, StaffScoped)
                    and context.staff.id == staff_id
                ),
            )
            self._add_range(start=home, until=until, content=True)
        elif kind in _LOUDNESS_KINDS:
            voice_id: object = row.get("voice_id")
            until = self._next_measure(
                start=home,
                matches=lambda context: (
                    isinstance(context, DynamicChange) and context.voice.id == voice_id
                ),
            )
            if until is not None:
                end: str | None = self._end_of(row=row, end_after=end_after)
                if end is None or end not in self._order:
                    until = None
                else:
                    until = max(until, self._order[end])
            self._add_range(start=home, until=until, content=False)
            # a hairpin of the same voice shows the levels it goes from and to
            for context in self._contexts_after():
                if isinstance(context, Hairpin) and context.voice.id == voice_id:
                    self._add_home(home=self._view.home_of(entity_id=context.id))
        elif kind in _TEMPO_KINDS:
            self._every_sound = True
            for context in self._contexts_after():
                if isinstance(context, TempoTransition):
                    self._add_home(home=self._view.home_of(entity_id=context.id))
        elif kind not in _DRAWN_KINDS:
            # the pedal, the repeats, the voltas and the jumps move the time of what follows
            self._every_sound = True

    def _read_note(self, *, note_id: str) -> None:
        """A note that changed changes the notes tied to it and the glissandos it ends or starts."""
        if self._entities is None:
            self._entities = EntityIndex(document=self._document)

        found: ScoreEntity | None = self._entities.find(entity_id=note_id)
        if not isinstance(found, Note):
            return

        seen: set[str] = {found.id}
        pending: list[Note] = [found]
        while pending:
            note: Note = pending.pop()
            for relation in note.relations:
                if isinstance(relation, Glissando):
                    for end in (relation.start, relation.end):
                        self._add_home(home=self._view.home_of(entity_id=end.id))
                elif isinstance(relation, Tie):
                    for tied in (relation.start, relation.end):
                        if tied.id not in seen:
                            seen.add(tied.id)
                            pending.append(tied)
                            self._add_home(home=self._view.home_of(entity_id=tied.id))

    def _read_placements(self, *, old: dict[str, Any], new: dict[str, Any]) -> None:
        for kind in old.keys() | new.keys():
            before: dict[str, Any] = {
                json.dumps(row, sort_keys=True): row for row in old.get(kind, [])
            }
            after: dict[str, Any] = {
                json.dumps(row, sort_keys=True): row for row in new.get(kind, [])
            }
            for key in before.keys() ^ after.keys():
                row: Any = before.get(key, after.get(key))
                home: str | None = self._home_of_any(entity_id=str(row["entity_id"]))
                if home is None:
                    self._header = True
                else:
                    self._content.add(home)

    def _contexts_after(self) -> list[Context]:
        if self._contexts is None:
            self._contexts = [
                context
                for measure in self._document.measures
                for anchor in measure.anchors
                for context in anchor.starting_contexts
            ]

        return self._contexts

    def _next_measure(self, *, start: str, matches: Any) -> int | None:
        """The index of the first measure after ``start`` with a context ``matches`` accepts;
        None when there is none (the reach goes to the end of the score)."""
        first: int = self._order.get(start, -1)
        found: int | None = None
        for context in self._contexts_after():
            index: int = self._order[context.start.measure.id]
            if index > first and matches(context) and (found is None or index < found):
                found = index

        return found

    def _end_of(self, *, row: Any, end_after: bool) -> str | None:
        """The measure a span context ends in: of the score after the edit or before it."""
        end_anchor_id: object = row.get("end_anchor_id")
        if end_anchor_id is None:
            return None

        if not end_after:
            return self._before.home(table="anchors", row_id=str(end_anchor_id))

        for context in self._contexts_after():
            if (
                isinstance(context, SpanContext)
                and isinstance(context, VoiceScoped)
                and context.end is not None
                and context.end.id == end_anchor_id
            ):
                return context.end.measure.id

        return None

    def _add_range(self, *, start: str, until: int | None, content: bool) -> None:
        if start not in self._order:
            self._every_sound = True
            if content:
                self._every_content = True
            return

        last: int = len(self._measure_ids) - 1 if until is None else until
        for measure_id in self._measure_ids[self._order[start] : last + 1]:
            self._sound.add(measure_id)
            if content:
                self._content.add(measure_id)


class _RecordHomes:
    """Where each entity of a record is kept with when its score is cut by measure, read from the
    rows of the record: an anchor names its measure, a container its anchor, a carrier its owner;
    a note is named by its carrier, a context by its anchor and a grace item by its group."""

    def __init__(self, *, record: DocumentRecord) -> None:
        self._tables: dict[str, dict[str, Any]] = record.get("tables", {})
        self._carrier_of_item: dict[str, str] | None = None
        self._anchor_of_context: dict[str, str] | None = None
        self._group_of_grace: dict[str, str] | None = None

    def home_of_entity(self, *, entity_id: str) -> str | None:
        for table in _ENTITY_TABLES:
            if entity_id in self._tables.get(table, {}):
                return self.home(table=table, row_id=entity_id)

        return None

    def home(self, *, table: str, row_id: str) -> str | None:
        row: Any = self._tables.get(table, {}).get(row_id)
        if row is None:
            return None

        if table == "measures":
            return row_id

        if table == "anchors":
            return str(row["measure_id"])

        if table == "rhythmic":
            return self.home(table="anchors", row_id=str(row["anchor_id"]))

        if table == "grace_groups":
            return self.home(table="rhythmic", row_id=str(row["leaf_id"]))

        if table == "grace_items":
            group_id: str | None = self._groups_of_graces().get(row_id)
            return None if group_id is None else self.home(table="grace_groups", row_id=group_id)

        if table == "carriers":
            owner_id: str = str(row["owner_id"])
            owner_table: str = (
                "rhythmic" if owner_id in self._tables.get("rhythmic", {}) else "grace_items"
            )
            return self.home(table=owner_table, row_id=owner_id)

        if table == "musical_items":
            carrier_id: str | None = self._carriers_of_items().get(row_id)
            return None if carrier_id is None else self.home(table="carriers", row_id=carrier_id)

        if table == "relations":
            if row.get("kind") == "beam":
                return self.home(table="carriers", row_id=str(row["carrier_ids"][0]))
            return self.home(table="musical_items", row_id=str(row["start_note_id"]))

        if table == "contexts":
            anchor_id: str | None = self._anchors_of_contexts().get(row_id)
            return None if anchor_id is None else self.home(table="anchors", row_id=anchor_id)

        return None

    def _carriers_of_items(self) -> dict[str, str]:
        if self._carrier_of_item is None:
            self._carrier_of_item = {}
            for carrier_id, carrier in self._tables.get("carriers", {}).items():
                for item_id in carrier.get("note_ids", []):
                    self._carrier_of_item[str(item_id)] = carrier_id
                if carrier.get("rest_id") is not None:
                    self._carrier_of_item[str(carrier["rest_id"])] = carrier_id

        return self._carrier_of_item

    def _anchors_of_contexts(self) -> dict[str, str]:
        if self._anchor_of_context is None:
            self._anchor_of_context = {}
            for anchor_id, anchor in self._tables.get("anchors", {}).items():
                for context_id in anchor.get("context_ids", []):
                    self._anchor_of_context[str(context_id)] = anchor_id

        return self._anchor_of_context

    def _groups_of_graces(self) -> dict[str, str]:
        if self._group_of_grace is None:
            self._group_of_grace = {}
            for group_id, group in self._tables.get("grace_groups", {}).items():
                for item_id in group.get("grace_item_ids", []):
                    self._group_of_grace[str(item_id)] = group_id

        return self._group_of_grace
