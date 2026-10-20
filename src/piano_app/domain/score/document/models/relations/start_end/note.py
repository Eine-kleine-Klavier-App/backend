from dataclasses import dataclass
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.score.document.models.notation import GlissandoType
from piano_app.domain.shared.abstract import abstract

from .base import StartEndRelation

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.material.primitive import Note


@abstract
@dataclass(slots=True, kw_only=True, eq=False)
class NoteToNoteRelation(StartEndRelation["Note"]):
    def attach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        self.start.add_relation(relation=self, sink=sink)
        self.end.add_relation(relation=self, sink=sink)

    def detach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        self.start.remove_relation(relation=self, sink=sink)
        self.end.remove_relation(relation=self, sink=sink)

    def set_start(self, *, start_note: Note, sink: MutationSink = DIRECT_SINK) -> None:
        """Move the relation's start to another note, keeping the relation itself."""
        if start_note is self.end:
            raise ValueError("Start and end must be different entities.")

        self.start.remove_relation(relation=self, sink=sink)
        sink.set_field(self, "_start", start_note)
        start_note.add_relation(relation=self, sink=sink)


@dataclass(slots=True, kw_only=True, eq=False)
class Tie(NoteToNoteRelation):
    def _validate_available_notes(self, *, start_note: Note) -> None:
        if any(
            isinstance(relation, Tie)
            for relation in start_note.relations
            if relation is not self and relation.start is start_note
        ):
            raise ValueError("Note already starts another tie.")

        if any(
            isinstance(relation, Tie)
            for relation in self.end.relations
            if relation is not self and relation.end is self.end
        ):
            raise ValueError("Note already ends another tie.")

    @classmethod
    def create(
        cls,
        *,
        start_note: Note,
        end_note: Note,
        sink: MutationSink = DIRECT_SINK,
    ) -> Tie:
        relation: Tie = cls(_start=start_note, _end=end_note)
        relation._validate_available_notes(start_note=start_note)

        relation.attach(sink=sink)
        return relation

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        start_note: Note,
        end_note: Note,
        sink: MutationSink = DIRECT_SINK,
    ) -> Tie:
        relation: Tie = cls(id=id, _start=start_note, _end=end_note)
        relation._validate_available_notes(start_note=start_note)

        relation.attach(sink=sink)
        return relation

    def attach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        self._validate_available_notes(start_note=self.start)
        super().attach(sink=sink)

    def set_start(self, *, start_note: Note, sink: MutationSink = DIRECT_SINK) -> None:
        self._validate_available_notes(start_note=start_note)
        super().set_start(start_note=start_note, sink=sink)


@dataclass(slots=True, kw_only=True, eq=False)
class Glissando(NoteToNoteRelation):
    _glissando_type: GlissandoType

    @property
    def glissando_type(self) -> GlissandoType:
        return self._glissando_type

    @classmethod
    def create(
        cls,
        *,
        start_note: Note,
        end_note: Note,
        glissando_type: GlissandoType,
        sink: MutationSink = DIRECT_SINK,
    ) -> Glissando:
        relation: Glissando = cls(
            _start=start_note,
            _end=end_note,
            _glissando_type=glissando_type,
        )

        relation.attach(sink=sink)
        return relation

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        start_note: Note,
        end_note: Note,
        glissando_type: GlissandoType,
        sink: MutationSink = DIRECT_SINK,
    ) -> Glissando:
        relation: Glissando = cls(
            id=id,
            _start=start_note,
            _end=end_note,
            _glissando_type=glissando_type,
        )

        relation.attach(sink=sink)
        return relation
