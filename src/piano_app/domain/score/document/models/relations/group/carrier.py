from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.shared.abstract import abstract

from .base import GroupRelation

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.material.carrier import Carrier


@abstract
@dataclass(slots=True, kw_only=True, eq=False)
class CarrierGroupRelation(GroupRelation["Carrier"]):
    def attach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        for carrier in self._members:
            carrier.add_carrier_group_relation(relation=self, sink=sink)

    def detach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        for carrier in self._members:
            carrier.remove_carrier_group_relation(relation=self, sink=sink)

    def remove_carrier(
        self,
        *,
        carrier: Carrier,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        if carrier not in self._members:
            if self in carrier.carrier_group_relations:
                raise ValueError("Carrier group relation references a non-member carrier.")

            return

        if self not in carrier.carrier_group_relations:
            raise ValueError("Carrier group relation is missing from the carrier.")

        if not self.can_remove_carrier(carrier=carrier):
            raise ValueError("Cannot remove carrier without invalidating its group relation.")

        carrier.remove_carrier_group_relation(relation=self, sink=sink)
        sink.list_remove(self, "_members", carrier)

    def can_remove_carrier(self, *, carrier: Carrier) -> bool:
        if carrier not in self._members:
            raise ValueError("Carrier is not a member of this group relation.")

        return len(self._members) > 1


@dataclass(slots=True, kw_only=True, eq=False)
class Beam(CarrierGroupRelation):
    @classmethod
    def create(
        cls,
        *,
        carriers: list[Carrier],
        sink: MutationSink = DIRECT_SINK,
    ) -> Beam:
        beam: Beam = cls(_members=list(carriers))

        beam.attach(sink=sink)
        return beam

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        carriers: list[Carrier],
        sink: MutationSink = DIRECT_SINK,
    ) -> Beam:
        beam: Beam = cls(id=id, _members=list(carriers))

        beam.attach(sink=sink)
        return beam

    def attach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        for carrier in self._members:
            self._validate_available_carrier(carrier=carrier)

        super().attach(sink=sink)

    def narrow_to(
        self,
        *,
        carriers: Sequence[Carrier],
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        """Keep only ``carriers``, a run of at least two consecutive members; the others
        leave the beam."""
        if len(carriers) < 2:
            raise ValueError("Beam must contain at least two carriers.")

        start: int = next(
            (index for index, member in enumerate(self._members) if member is carriers[0]),
            -1,
        )

        if start < 0 or self._members[start : start + len(carriers)] != list(carriers):
            raise ValueError("A beam is narrowed only to a run of its consecutive members.")

        leaving: list[Carrier] = [member for member in self._members if member not in carriers]
        for carrier in leaving:
            carrier.remove_carrier_group_relation(relation=self, sink=sink)
            sink.list_remove(self, "_members", carrier)

    def can_remove_carrier(self, *, carrier: Carrier) -> bool:
        if carrier not in self._members:
            raise ValueError("Carrier is not a member of this beam.")

        return len(self._members) > 2

    def _validate_available_carrier(self, *, carrier: Carrier) -> None:
        if any(
            isinstance(group_relation, Beam)
            for group_relation in carrier.carrier_group_relations
            if group_relation is not self
        ):
            raise ValueError("Carrier is already part of another beam.")
