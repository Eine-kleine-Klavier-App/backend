from bisect import bisect_right
from dataclasses import dataclass
from fractions import Fraction

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import (
    ClefChange,
    KeySignatureChange,
    OctaveTransposition,
)
from piano_app.domain.score.document.models.material import Carrier, Note, NoteCarrier
from piano_app.domain.score.document.models.notation import Accidental, Clef
from piano_app.domain.score.document.models.structural import Measure, Staff, TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.models.structural.rhythm.grace import GraceItem
from piano_app.domain.score.document.services.contexts import ContextIndex, Scope
from piano_app.domain.score.document.services.geometry import Piece, Point
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.indexing import Index

from .errors import PitchResolutionError
from .modifiers import in_force
from .regions import OctaveRegion, PitchRegion
from .resolver import PitchResolver
from .sign_cell import SignCell
from .transform import PitchTransform
from .values import Pitch

# This is the only module in pitch that knows the score model.
# Origins name the diatonic position of the bottom staff line, with zero at MIDI zero.
_CLEF_ORIGINS: dict[Clef, int] = {Clef.TREBLE: 37, Clef.BASS: 25}
_ACCIDENTALS: dict[Accidental, int] = {
    Accidental.DOUBLE_FLAT: -2,
    Accidental.FLAT: -1,
    Accidental.NATURAL: 0,
    Accidental.SHARP: 1,
    Accidental.DOUBLE_SHARP: 2,
}


@dataclass(frozen=True, slots=True)
class _Signs:
    """The signs written on the notes standing on one staff step of one staff in one measure:
    where in the measure each stands (the position of its anchor and its cell), in reading
    order, and which accidental it carries."""

    places: tuple[tuple[Fraction, SignCell], ...]
    accidentals: tuple[Accidental, ...]


@dataclass(frozen=True, slots=True)
class _MeasureSigns:
    """The signs of one measure by staff and staff step, and the anchors they were read from."""

    anchors: tuple[TemporalAnchor, ...]
    by_step: dict[tuple[Staff, int], _Signs]


class ScorePitch(Index):
    """A lazy pitch index over a document, that document's live geometry and its contexts.

    Each staff owns a fragment of rules, composed from the pieces the context index answers
    for the modifiers of pitch (``MODIFIERS``). Beside them it keeps, per measure, the signs of
    the notes and grace notes by staff and staff step in reading order, so the sign in force is one
    lookup; the key signature is not copied, it is read from the context index. Notify this
    index after changing contexts or their coordinates, the geometry and the context index
    before it. Reads after those notifications rebuild only what they need. Returned pitches
    are snapshots, not values to hold across a mutation.
    """

    def __init__(
        self,
        *,
        document: ScoreDocument,
        geometry: ScoreGeometry,
        contexts: ContextIndex,
    ) -> None:
        self._document: ScoreDocument = document
        self._geometry: ScoreGeometry = geometry
        self._contexts: ContextIndex = contexts
        self._staffs: dict[Staff, PitchResolver] = {}
        self._signs: dict[Measure, _MeasureSigns] = {}
        self._measure_of_anchor: dict[TemporalAnchor, Measure] = {}

    def resolve(
        self,
        *,
        staff: Staff,
        point: Point,
        staff_step: int,
        accidental: Accidental,
    ) -> Pitch:
        if staff not in self._document.staffs:
            raise ValueError("Staff is not in the pitch index's document.")
        position: Point = point.to(frame=self._geometry.root)

        return self._read_staff(staff=staff).resolve(
            point=position, staff_step=staff_step, accidental=_ACCIDENTALS[accidental]
        )

    def accidental_at(
        self,
        *,
        staff: Staff,
        point: Point,
        staff_step: int,
        cell: SignCell,
    ) -> Accidental:
        """Infer a concrete sign from earlier notation on this line, then the active key.

        The last sign on this staff step in the measure the point falls in, across voices, up to
        and including the cell of the thing being written at that point — by the anchor's
        position in the measure, so tuplet scale and earlier measures do not matter — read from
        the measure's signs; else the key signature by the active clef, read from the context
        index. A note reads the grace notes before it and the notes of every voice at its anchor,
        not the grace notes after it; a grace note reads what stands up to its own cell.
        """
        if staff not in self._document.staffs:
            raise ValueError("Staff is not in the pitch index's document.")
        position = point.to(frame=self._geometry.root)
        measure = self._geometry.measure_at(point=position)
        if measure is None:
            raise ValueError("Accidental point is outside the score timeline.")

        local: Fraction = position.value - self._geometry.measure_span(measure=measure).start
        signs: _Signs | None = self._read_signs(measure=measure).by_step.get((staff, staff_step))
        if signs is not None:
            reached: int = bisect_right(signs.places, (local, cell))
            if reached > 0:
                return signs.accidentals[reached - 1]

        scope: Scope = Scope.of_staff(staff=staff)
        key: KeySignatureChange | None = self._contexts.piece_at(
            kind=KeySignatureChange, point=position.value, scope=scope
        ).value
        clef: ClefChange | None = self._contexts.piece_at(
            kind=ClefChange, point=position.value, scope=scope
        ).value
        if key is None:
            return Accidental.NATURAL
        if clef is None:
            raise PitchResolutionError("No clef rule covers the accidental point.")
        step = (_CLEF_ORIGINS[clef.clef] + staff_step) % 7
        return key.alterations[step]

    def pitch_of(self, *, note: Note) -> Pitch:
        """The pitch of a note of a metric leaf, or of a grace note of one, read at the leaf's
        start."""
        owner: object = note.note_carrier.owner
        if isinstance(owner, GraceItem):
            owner = owner.grace_group.leaf

        if not isinstance(owner, LeafRhythmicContainer):
            raise ValueError("Only the pitch of a note in a metric leaf is resolved.")

        return self.resolve(
            staff=note.staff,
            point=self._geometry.point_of(anchor=owner.anchor),
            staff_step=note.staff_step,
            accidental=note.accidental,
        )

    def staff_step_for(
        self,
        *,
        staff: Staff,
        point: Point,
        midi_note: int,
        accidental: Accidental,
    ) -> int:
        """The staff step that sounds ``midi_note`` with the accidental on a staff at a point."""
        if staff not in self._document.staffs:
            raise ValueError("Staff is not in the pitch index's document.")

        return self._read_staff(staff=staff).staff_step_for(
            point=point.to(frame=self._geometry.root),
            midi_note=midi_note,
            accidental=_ACCIDENTALS[accidental],
        )

    def invalidate_staff(self, *, staff: Staff) -> None:
        """A pitch context on this staff was created, removed, changed or moved."""
        self._staffs.pop(staff, None)

    def invalidate_anchor(self, *, anchor: TemporalAnchor) -> None:
        """An anchor moved; both the contexts starting and ending there are affected."""
        staffs: set[Staff] = {
            context.staff
            for context in (*anchor.starting_contexts, *anchor.ending_contexts)
            if isinstance(context, (ClefChange, OctaveTransposition))
        }
        for staff in staffs:
            self.invalidate_staff(staff=staff)

        # the signs of the measure it stood in, and of the one it stands in now
        self._drop_signs(measure=self._measure_of_anchor.get(anchor))
        self._drop_signs(measure=anchor.measure)

    def invalidate_leaf(self, *, leaf: LeafRhythmicContainer) -> None:
        """A leaf was created, deleted or resized: the notes of its measure may have changed."""
        self._drop_signs(measure=leaf.anchor.measure)

    def invalidate_note(self, *, note: Note) -> None:
        """A note was created, deleted, moved or given another sign: the signs of its measure
        are stale, for every staff of it."""
        owner: object = note.note_carrier.owner
        if isinstance(owner, GraceItem):
            owner = owner.grace_group.leaf
        if isinstance(owner, LeafRhythmicContainer):
            self._drop_signs(measure=owner.anchor.measure)

    def invalidate_measures(self) -> None:
        """The measure chain or its lengths changed, shifting context coordinates. The signs
        stay: each is kept by its place inside its own measure, which no other measure moves."""
        self._staffs.clear()

    def _drop_signs(self, *, measure: Measure | None) -> None:
        cached: _MeasureSigns | None = None if measure is None else self._signs.pop(measure, None)
        if cached is not None:
            for anchor in cached.anchors:
                self._measure_of_anchor.pop(anchor, None)

    def _read_signs(self, *, measure: Measure) -> _MeasureSigns:
        cached: _MeasureSigns | None = self._signs.get(measure)
        if cached is None:
            found: dict[tuple[Staff, int], dict[tuple[Fraction, SignCell], Accidental]] = {}
            for anchor in measure.anchors:
                self._measure_of_anchor[anchor] = measure
                at: Fraction = anchor.position.value
                for container in anchor.containers:
                    if not isinstance(container, LeafRhythmicContainer):
                        continue

                    carriers: list[tuple[SignCell, Carrier | None]] = []
                    if container.grace_before is not None:
                        for grace in container.grace_before.grace_items:
                            carriers.append((SignCell.BEFORE, grace.carrier))
                    carriers.append((SignCell.NOTE, container.carrier))
                    if container.grace_after is not None:
                        for grace in container.grace_after.grace_items:
                            carriers.append((SignCell.AFTER, grace.carrier))

                    for cell, carrier in carriers:
                        if not isinstance(carrier, NoteCarrier):
                            continue

                        for item in carrier.notes:
                            step: tuple[Staff, int] = (item.staff, item.staff_step)
                            signs_of_step = found.setdefault(step, {})
                            place: tuple[Fraction, SignCell] = (at, cell)
                            # the first note on a step at an anchor stands; of the grace notes
                            # the last does, since the next one reads it
                            if cell is not SignCell.NOTE or place not in signs_of_step:
                                signs_of_step[place] = item.accidental

            by_step: dict[tuple[Staff, int], _Signs] = {}
            for step, signs in found.items():
                ordered: list[tuple[Fraction, SignCell]] = sorted(signs)
                by_step[step] = _Signs(
                    places=tuple(ordered),
                    accidentals=tuple(signs[place] for place in ordered),
                )

            cached = _MeasureSigns(anchors=tuple(measure.anchors), by_step=by_step)
            self._signs[measure] = cached

        return cached

    def _read_staff(self, *, staff: Staff) -> PitchResolver:
        resolver: PitchResolver | None = self._staffs.get(staff)
        if resolver is None:
            scope: Scope = Scope.of_staff(staff=staff)
            extent: Fraction = self._geometry.root.extent

            regions: list[PitchRegion] = []
            clef_pieces: list[Piece[ClefChange | None, ClefChange]] = self._contexts.pieces_over(
                kind=ClefChange, start=Fraction(0), end=extent, scope=scope
            )
            for piece in clef_pieces:
                for clef in in_force(kind=ClefChange, piece=piece):
                    regions.append(
                        PitchRegion(
                            span=piece.span,
                            transform=PitchTransform(
                                diatonic_origin=_CLEF_ORIGINS[clef.clef],
                                octaves=clef.octave_transposition,
                            ),
                        )
                    )

            octave_regions: list[OctaveRegion] = []
            octave_pieces: list[Piece[OctaveTransposition | None, OctaveTransposition]] = (
                self._contexts.pieces_over(
                    kind=OctaveTransposition, start=Fraction(0), end=extent, scope=scope
                )
            )
            for octave_piece in octave_pieces:
                lines: tuple[OctaveTransposition, ...] = in_force(
                    kind=OctaveTransposition, piece=octave_piece
                )
                if lines:
                    octave_regions.append(
                        OctaveRegion(
                            span=octave_piece.span,
                            octaves=sum(line.octaves for line in lines),
                        )
                    )

            resolver = PitchResolver(
                frame=self._geometry.root, regions=regions, octave_regions=octave_regions
            )
            self._staffs[staff] = resolver

        return resolver
