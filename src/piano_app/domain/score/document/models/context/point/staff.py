from dataclasses import dataclass
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.score.document.models.notation import Accidental, Clef

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


# one entry per diatonic step, in the order C D E F G A B
KEY_SIGNATURE_STEPS: int = 7
NO_ACCIDENTALS: tuple[Accidental, ...] = (Accidental.NATURAL,) * KEY_SIGNATURE_STEPS
# a key signature has no double accidentals
KEY_SIGNATURE_ACCIDENTALS: frozenset[Accidental] = frozenset(
    {Accidental.FLAT, Accidental.NATURAL, Accidental.SHARP}
)


@dataclass(kw_only=True, eq=False)
class KeySignatureChange(StaffScoped, PointContext):
    """A key signature: the accidental of each of the seven diatonic steps, independent of the
    clef. Natural everywhere is the key signature of nothing."""

    _alterations: tuple[Accidental, ...] = NO_ACCIDENTALS

    @property
    def alterations(self) -> tuple[Accidental, ...]:
        return self._alterations

    def _check_invariants(self) -> None:
        super()._check_invariants()

        if len(self._alterations) != KEY_SIGNATURE_STEPS:
            raise ValueError(f"Key signature must give {KEY_SIGNATURE_STEPS} alterations.")

        for alteration in self._alterations:
            if alteration not in KEY_SIGNATURE_ACCIDENTALS:
                raise ValueError("A key signature has no double accidentals.")

    @classmethod
    def create(
        cls,
        *,
        start: TemporalAnchor,
        staff: Staff,
        alterations: tuple[Accidental, ...] = NO_ACCIDENTALS,
        sink: MutationSink = DIRECT_SINK,
    ) -> KeySignatureChange:
        key_signature_change = cls(_start=start, _staff=staff, _alterations=alterations)

        key_signature_change.attach(sink=sink)
        return key_signature_change

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        start: TemporalAnchor,
        staff: Staff,
        alterations: tuple[Accidental, ...] = NO_ACCIDENTALS,
        sink: MutationSink = DIRECT_SINK,
    ) -> KeySignatureChange:
        key_signature_change = cls(id=id, _start=start, _staff=staff, _alterations=alterations)

        key_signature_change.attach(sink=sink)
        return key_signature_change
