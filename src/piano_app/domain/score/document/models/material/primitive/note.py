from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.score.document.models.notation import Accidental, Fingering

from .base import MusicalItem

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.material.carrier import NoteCarrier
    from piano_app.domain.score.document.models.relations.start_end import NoteToNoteRelation
    from piano_app.domain.score.document.models.structural import Staff


@dataclass(slots=True, kw_only=True, eq=False)
class Note(MusicalItem):
    """A representation of a musical note, only notation, pitch is derived on demand.

    Staff step index: 0 is the first line, 1 is the first gap above it, -1 is the gap
    below the first line.
    """

    _staff_step: int
    _accidental: Accidental
    _fingering: Fingering = Fingering.NONE

    _note_carrier: NoteCarrier
    _relations: list[NoteToNoteRelation] = field(default_factory=list)

    @property
    def staff_step(self) -> int:
        return self._staff_step

    @property
    def accidental(self) -> Accidental:
        return self._accidental

    @property
    def fingering(self) -> Fingering:
        return self._fingering

    @property
    def note_carrier(self) -> NoteCarrier:
        return self._note_carrier

    @property
    def relations(self) -> Sequence[NoteToNoteRelation]:
        return self._relations

    @classmethod
    def create(
        cls,
        *,
        note_carrier: NoteCarrier,
        staff: Staff,
        staff_step: int,
        accidental: Accidental,
        fingering: Fingering = Fingering.NONE,
        sink: MutationSink = DIRECT_SINK,
    ) -> Note:
        note: Note = cls(
            _staff_step=staff_step,
            _staff=staff,
            _note_carrier=note_carrier,
            _accidental=accidental,
            _fingering=fingering,
        )

        note.attach(sink=sink)
        return note

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        note_carrier: NoteCarrier,
        staff: Staff,
        staff_step: int,
        accidental: Accidental,
        fingering: Fingering = Fingering.NONE,
        sink: MutationSink = DIRECT_SINK,
    ) -> Note:
        note: Note = cls(
            id=id,
            _staff_step=staff_step,
            _staff=staff,
            _note_carrier=note_carrier,
            _accidental=accidental,
            _fingering=fingering,
        )

        note.attach(sink=sink)
        return note

    def set_fingering(self, *, fingering: Fingering, sink: MutationSink = DIRECT_SINK) -> None:
        sink.set_field(self, "_fingering", fingering)

    def set_accidental(self, *, accidental: Accidental, sink: MutationSink = DIRECT_SINK) -> None:
        sink.set_field(self, "_accidental", accidental)

    def set_staff_step(self, *, staff_step: int, sink: MutationSink = DIRECT_SINK) -> None:
        """Move the note to another place on its staff, which changes what it sounds."""
        sink.set_field(self, "_staff_step", staff_step)

    def attach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        super().attach(sink=sink)
        self._note_carrier.add_note(note=self, sink=sink)

    def detach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        self._note_carrier.remove_note(note=self, sink=sink)
        super().detach(sink=sink)

    def add_relation(
        self,
        *,
        relation: NoteToNoteRelation,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if relation.start is not self and relation.end is not self:
            raise ValueError("Relation must be connected to this note.")

        if relation in self._relations:
            return

        sink.list_append(self, "_relations", relation)

    def remove_relation(
        self,
        *,
        relation: NoteToNoteRelation,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if relation.start is not self and relation.end is not self:
            raise ValueError("Relation must be connected to this note.")

        if relation not in self._relations:
            return

        sink.list_remove(self, "_relations", relation)
