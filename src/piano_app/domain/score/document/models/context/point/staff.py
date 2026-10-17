from dataclasses import dataclass
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.score.document.models.notation import Clef, KeySignatureAccidental

from ..scope import StaffScoped
from .base import PointContext

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.structural import Staff, TemporalAnchor


@dataclass(kw_only=True, eq=False)
class ClefChange(StaffScoped, PointContext):
    _clef: Clef
    _octave_transposition: int = 0

    @property
    def clef(self) -> Clef:
        return self._clef

    @property
    def octave_transposition(self) -> int:
        return self._octave_transposition

    @classmethod
    def create(
        cls,
        *,
        start: TemporalAnchor,
        staff: Staff,
        clef: Clef,
        octave_transposition: int = 0,
        sink: MutationSink = DIRECT_SINK,
    ) -> ClefChange:
        clef_change = cls(
            _start=start,
            _staff=staff,
            _clef=clef,
            _octave_transposition=octave_transposition,
        )

        clef_change.attach(sink=sink)
        return clef_change

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        start: TemporalAnchor,
        staff: Staff,
        clef: Clef,
        octave_transposition: int = 0,
        sink: MutationSink = DIRECT_SINK,
    ) -> ClefChange:
        clef_change = cls(
            id=id,
            _start=start,
            _staff=staff,
            _clef=clef,
            _octave_transposition=octave_transposition,
        )

        clef_change.attach(sink=sink)
        return clef_change


@dataclass(frozen=True, slots=True, kw_only=True)
class KeySignatureSymbol:
    staff_step: int
    accidental: KeySignatureAccidental


@dataclass(kw_only=True, eq=False)
class KeySignatureChange(StaffScoped, PointContext):
    _symbols: tuple[KeySignatureSymbol, ...] = ()

    @property
    def symbols(self) -> tuple[KeySignatureSymbol, ...]:
        return self._symbols

    def _check_invariants(self) -> None:
        super()._check_invariants()

        steps: list[int] = [symbol.staff_step for symbol in self._symbols]
        if len(steps) != len(set(steps)):
            raise ValueError("Key signature symbols must not repeat a staff step.")

    @classmethod
    def create(
        cls,
        *,
        start: TemporalAnchor,
        staff: Staff,
        symbols: tuple[KeySignatureSymbol, ...] = (),
        sink: MutationSink = DIRECT_SINK,
    ) -> KeySignatureChange:
        key_signature_change = cls(_start=start, _staff=staff, _symbols=symbols)

        key_signature_change.attach(sink=sink)
        return key_signature_change

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        start: TemporalAnchor,
        staff: Staff,
        symbols: tuple[KeySignatureSymbol, ...] = (),
        sink: MutationSink = DIRECT_SINK,
    ) -> KeySignatureChange:
        key_signature_change = cls(id=id, _start=start, _staff=staff, _symbols=symbols)

        key_signature_change.attach(sink=sink)
        return key_signature_change
