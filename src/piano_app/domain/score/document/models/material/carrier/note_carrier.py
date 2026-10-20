from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.score.document.models.notation import (
    Articulation,
    Ornament,
    check_articulations,
)

from .base import Carrier

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.material.carrier_owner import CarrierOwner
    from piano_app.domain.score.document.models.material.primitive.note import Note


# TODO validate note addition by absolute pitch. Pitch may be a key for dict
@dataclass(slots=True, kw_only=True, eq=False)
class NoteCarrier(Carrier):
    _articulations: frozenset[Articulation] = frozenset()
    _ornament: Ornament = Ornament.NONE

    _notes: list[Note] = field(default_factory=list)

    @property
    def articulations(self) -> frozenset[Articulation]:
        return self._articulations

    @property
    def ornament(self) -> Ornament:
        return self._ornament

    @property
    def notes(self) -> Sequence[Note]:
        return self._notes

    @classmethod
    def create(
        cls,
        *,
        owner: CarrierOwner,
        articulations: frozenset[Articulation] = frozenset(),
        ornament: Ornament = Ornament.NONE,
        sink: MutationSink = DIRECT_SINK,
    ) -> NoteCarrier:
        check_articulations(articulations=articulations)
        carrier: NoteCarrier = cls(
            _owner=owner,
            _articulations=articulations,
            _ornament=ornament,
        )

        carrier.attach(sink=sink)
        return carrier

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        owner: CarrierOwner,
        articulations: frozenset[Articulation] = frozenset(),
        ornament: Ornament = Ornament.NONE,
        sink: MutationSink = DIRECT_SINK,
    ) -> NoteCarrier:
        carrier: NoteCarrier = cls(
            id=id,
            _owner=owner,
            _articulations=articulations,
            _ornament=ornament,
        )

        carrier.attach(sink=sink)
        return carrier

    def set_articulations(
        self,
        *,
        articulations: frozenset[Articulation],
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        check_articulations(articulations=articulations)
        sink.set_field(self, "_articulations", articulations)

    def set_ornament(
        self,
        *,
        ornament: Ornament,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        sink.set_field(self, "_ornament", ornament)

    def detach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        if any(
            not relation.can_remove_carrier(carrier=self)
            for relation in self._carrier_group_relations
        ):
            raise ValueError("Cannot detach note carrier without invalidating a group relation.")

        super().detach(sink=sink)

    def add_note(
        self,
        *,
        note: Note,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if note.note_carrier is not self:
            raise ValueError("Cannot add note that belongs to another note carrier.")

        if note in self._notes:
            return

        sink.list_append(self, "_notes", note)

    def remove_note(
        self,
        *,
        note: Note,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if note.note_carrier is not self:
            raise ValueError("Cannot remove note that is not in this note carrier.")

        if note not in self._notes:
            return

        if note.relations:
            raise ValueError("Cannot remove note while it belongs to a relation.")

        sink.list_remove(self, "_notes", note)
