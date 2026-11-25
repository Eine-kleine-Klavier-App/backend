from bisect import bisect_right
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction

from piano_app.application.ports.importing import (
    ImportIssue,
    IssueKind,
    SourceBarline,
    SourceDynamic,
    SourceMeasure,
    SourceNote,
    SourceScore,
)
from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import OctaveTransposition
from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import (
    ARTICULATION_CATEGORIES,
    Articulation,
    ArticulationCategory,
    DottedRhythmicValue,
    DynamicMarking,
    Fingering,
    Ornament,
)
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation import MutationCompiler, MutationEngine
from piano_app.domain.score.document.services.mutation.compiler import (
    CarrierMarks,
    CreateHairpinIntent,
    CreateOctaveTranspositionIntent,
    CreateRefrainIntent,
    CreateSlurIntent,
    CreateSustainHoldIntent,
    CreateVoltaIntent,
    EditIntent,
    OpenContextEndIntent,
    PitchEditMode,
    SetCarrierMarksIntent,
    SetDynamicIntent,
    SetFingeringIntent,
    SetTempoIntent,
    VoltaFragmentIntent,
)
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch

from .lookup import LeafKey, NoteKey, leaf_index, note_index
from .mappings import NOTE_TYPES, midi_of

# Where something stands in the source: the measure's 0-based index and the quarter notes from its
# start. It may lie at the end of a measure or past it (a mark that stops after the last note).
Place = tuple[int, Fraction]

_QUARTERS_PER_WHOLE: int = 4
_INITIAL_DYNAMIC: DynamicMarking = DynamicMarking.PIANO
_DEFAULT_REPEAT_TIMES: int = 2

_ARTICULATIONS: dict[str, Articulation] = {
    "staccato": Articulation.STACCATO,
    "staccatissimo": Articulation.STACCATISSIMO,
    "tenuto": Articulation.TENUTO,
    "accent": Articulation.ACCENT,
    "strong-accent": Articulation.MARCATO,
    "fermata": Articulation.FERMATA,
    "arpeggio-up": Articulation.ARPEGGIO_UP,
    "arpeggio-down": Articulation.ARPEGGIO_DOWN,
}

# MusicXML calls a mordent with the line through it a "mordent" (lower) and without it an
# "inverted-mordent" (upper), the other way round from the usual teaching; the score names them
# by the note they touch.
_ORNAMENTS: dict[str, Ornament] = {
    "trill-mark": Ornament.TRILL,
    "mordent": Ornament.LOWER_MORDENT,
    "inverted-mordent": Ornament.UPPER_MORDENT,
    "turn": Ornament.TURN,
    "inverted-turn": Ornament.INVERTED_TURN,
    "tremolo-1": Ornament.TREMOLO_1,
    "tremolo-2": Ornament.TREMOLO_2,
    "tremolo-3": Ornament.TREMOLO_3,
}

_OCTAVES_OF_SIZE: dict[int, int] = {8: 1, 15: 2}


@dataclass(frozen=True, slots=True, kw_only=True)
class _Dynamic:
    place: Place
    marking: DynamicMarking
    staff: int | None
    """The staff it is for when the file puts different ones at the place on the two staffs;
    ``None`` for one the whole piece takes, which is the only one there or the same on both."""


@dataclass(frozen=True, slots=True, kw_only=True)
class _Item:
    """One thing to put in: what it is, the measure of the file it stands in, and the intent."""

    measure: str
    what: str
    intent: EditIntent
    parts: tuple[EditIntent, ...] = ()
    """When the item is refused as a whole: the smaller intents it is tried as, one by one."""


@dataclass(frozen=True, slots=True, kw_only=True)
class _Ending:
    first: int
    last: int
    passes: tuple[int, ...]
    closes_repeat: bool
    times: int | None


class MarkPlacer:
    """Puts what stands between the notes into the built score: octave lines (before the notes,
    since they say how a note's pitch is written), then dynamics, tempos, hairpins, slurs,
    pedals, repeats and endings, then the articulations, ornaments and fingerings of the notes.

    Every kind goes in its own transaction. When one is refused, the items of the kind are tried
    one by one and only the refused ones are left out and reported, so a mark the score has no
    place for never costs the notes.
    """

    def __init__(self, *, engine: MutationEngine, compiler: MutationCompiler) -> None:
        self._engine: MutationEngine = engine
        self._compiler: MutationCompiler = compiler

    def place_octave_lines(
        self, *, document: ScoreDocument, source: SourceScore, issues: list[ImportIssue]
    ) -> None:
        lengths: list[Fraction] = _lengths(document=document)
        starts: list[Fraction] = _starts(document=document)
        items: list[_Item] = []
        to_the_end: list[tuple[int, Fraction]] = []

        for staff_number in range(1, len(document.staffs) + 1):
            open_line: tuple[Place, int, str] | None = None
            for index, measure in enumerate(source.measures):
                for shift in sorted(
                    (s for s in measure.octave_shifts if s.staff == staff_number),
                    key=lambda s: s.onset,
                ):
                    if shift.kind == "stop":
                        if open_line is None:
                            continue

                        start, octaves, number = open_line
                        open_line = None
                        end: tuple[int, MeasurePosition] | None = _locate(
                            place=(index, shift.onset), lengths=lengths
                        )
                        item: _Item | None = self._octave_item(
                            document=document,
                            staff_number=staff_number,
                            start=start,
                            end=end,
                            octaves=octaves,
                            number=number,
                            lengths=lengths,
                            starts=starts,
                            to_the_end=to_the_end,
                        )
                        if item is not None:
                            items.append(item)

                        continue

                    octaves_of_size: int | None = _OCTAVES_OF_SIZE.get(shift.size)
                    if octaves_of_size is None:
                        issues.append(
                            ImportIssue(
                                kind=IssueKind.SKIPPED,
                                measure=measure.number,
                                message=f"An octave line of {shift.size} steps is not imported.",
                            )
                        )
                        continue

                    # "down" in MusicXML draws the notes lower than they sound: 8va.
                    open_line = (
                        (index, shift.onset),
                        octaves_of_size if shift.kind == "down" else -octaves_of_size,
                        measure.number,
                    )

            if open_line is not None:
                start, octaves, number = open_line
                tail: _Item | None = self._octave_item(
                    document=document,
                    staff_number=staff_number,
                    start=start,
                    end=None,
                    octaves=octaves,
                    number=number,
                    lengths=lengths,
                    starts=starts,
                    to_the_end=to_the_end,
                )
                if tail is not None:
                    items.append(tail)

        self._run(document=document, items=items, issues=issues)
        self._open_to_the_end(document=document, lines=to_the_end, issues=issues)

    def place_contexts(
        self,
        *,
        document: ScoreDocument,
        source: SourceScore,
        voice_numbers: list[int],
        issues: list[ImportIssue],
    ) -> None:
        lengths: list[Fraction] = _lengths(document=document)
        # where each voice plays, staff by staff: a voice crosses between the staffs, so what a mark
        # of one staff is for is decided at the place of the mark
        plays: dict[int, list[tuple[Place, int]]] = {}
        for index, measure in enumerate(source.measures):
            for note in measure.notes:
                if not note.is_grace:
                    plays.setdefault(note.voice, []).append(((index, note.onset), note.staff))

        for played in plays.values():
            played.sort(key=lambda entry: entry[0])

        def voices_on(staff: int, place: Place) -> tuple[str, ...]:
            """The voices that are on the staff at the place: each on the staff of the note it
            plays there (the last that began at or before the place, else the first after it)."""
            return tuple(
                document.voices[voice_numbers.index(number)].id
                for number, played in sorted(plays.items())
                if played[max(bisect_right([where for where, _ in played], place) - 1, 0)][1]
                == staff
            )

        dynamics: list[_Dynamic] = self._dynamics(
            document=document, source=source, lengths=lengths, issues=issues
        )
        self._run(
            document=document,
            items=[
                *self._dynamic_items(
                    document=document,
                    dynamics=dynamics,
                    voices_on=voices_on,
                    source=source,
                    lengths=lengths,
                ),
                *self._tempo_items(
                    document=document, source=source, lengths=lengths, issues=issues
                ),
            ],
            issues=issues,
        )
        self._run(
            document=document,
            items=self._hairpin_items(
                document=document,
                source=source,
                dynamics=dynamics,
                voices_on=voices_on,
                lengths=lengths,
                issues=issues,
            ),
            issues=issues,
        )
        self._run(
            document=document,
            items=[
                *self._slur_items(
                    document=document,
                    source=source,
                    voice_numbers=voice_numbers,
                    lengths=lengths,
                    issues=issues,
                ),
                *self._pedal_items(
                    document=document, source=source, lengths=lengths, issues=issues
                ),
            ],
            issues=issues,
        )
        self._run(
            document=document,
            items=self._repeat_items(
                document=document, source=source, lengths=lengths, issues=issues
            ),
            issues=issues,
        )

    def place_marks(
        self,
        *,
        document: ScoreDocument,
        source: SourceScore,
        voice_numbers: list[int],
        issues: list[ImportIssue],
    ) -> None:
        geometry: ScoreGeometry = ScoreGeometry(document=document)
        contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
        pitch: ScorePitch = ScorePitch(document=document, geometry=geometry, contexts=contexts)
        leaves: dict[LeafKey, LeafRhythmicContainer] = leaf_index(document=document)
        notes: dict[NoteKey, Note] | None = None

        by_carrier: dict[str, tuple[set[Articulation], Ornament | None, str]] = {}
        fingerings: list[_Item] = []
        for index, measure in enumerate(source.measures):
            for source_note in measure.notes:
                has_marks: bool = bool(
                    source_note.articulations or source_note.ornament or source_note.fingering
                )
                if not has_marks:
                    continue

                if source_note.is_grace or source_note.pitch is None:
                    issues.append(
                        ImportIssue(
                            kind=IssueKind.SKIPPED,
                            measure=measure.number,
                            message="The marks of a grace note or of a rest are not imported.",
                        )
                    )
                    continue

                voice_index: int = voice_numbers.index(source_note.voice)
                position: Fraction = source_note.onset / _QUARTERS_PER_WHOLE
                leaf: LeafRhythmicContainer | None = leaves.get((voice_index, index, position))
                if leaf is None or not isinstance(leaf.carrier, NoteCarrier):
                    continue

                self._collect_marks(
                    source_note=source_note,
                    carrier_id=leaf.carrier.id,
                    measure=measure,
                    by_carrier=by_carrier,
                    issues=issues,
                )
                if source_note.fingering is None:
                    continue

                if notes is None:
                    notes = note_index(document=document, pitch=pitch)

                note: Note | None = notes.get(
                    (
                        voice_index,
                        source_note.staff - 1,
                        index,
                        position,
                        midi_of(pitch=source_note.pitch),
                    )
                )
                if note is not None:
                    fingerings.append(
                        _Item(
                            measure=measure.number,
                            what="A fingering",
                            intent=SetFingeringIntent(
                                note_id=note.id, fingering=Fingering(source_note.fingering)
                            ),
                        )
                    )

        # One intent for all the carriers: the compiler looks the carriers up in the score once.
        marks: list[CarrierMarks] = [
            CarrierMarks(
                carrier_id=carrier_id,
                articulations=frozenset(articulations),
                ornament=ornament,
            )
            for carrier_id, (articulations, ornament, _) in by_carrier.items()
        ]
        items: list[_Item] = []
        if marks:
            items.append(
                _Item(
                    measure=next(iter(by_carrier.values()))[2],
                    what="The marks of a note",
                    intent=SetCarrierMarksIntent(items=tuple(marks)),
                    parts=tuple(SetCarrierMarksIntent(items=(mark,)) for mark in marks),
                )
            )

        self._run(document=document, items=[*items, *fingerings], issues=issues)

    def _collect_marks(
        self,
        *,
        source_note: SourceNote,
        carrier_id: str,
        measure: SourceMeasure,
        by_carrier: dict[str, tuple[set[Articulation], Ornament | None, str]],
        issues: list[ImportIssue],
    ) -> None:
        articulations, ornament, _ = by_carrier.get(carrier_id, (set(), None, measure.number))
        taken: set[ArticulationCategory] = {ARTICULATION_CATEGORIES[a] for a in articulations}

        for name in (n for n in _ARTICULATIONS if n in source_note.articulations):
            mark: Articulation = _ARTICULATIONS[name]
            category: ArticulationCategory = ARTICULATION_CATEGORIES[mark]
            if mark in articulations:
                continue

            if category in taken:
                issues.append(
                    ImportIssue(
                        kind=IssueKind.SKIPPED,
                        measure=measure.number,
                        message=f"A note has one mark of its kind only: {name} is not imported.",
                    )
                )
                continue

            taken.add(category)
            articulations.add(mark)

        if source_note.ornament is not None and ornament is None:
            ornament = _ORNAMENTS.get(source_note.ornament)
            if ornament is None:
                issues.append(
                    ImportIssue(
                        kind=IssueKind.SKIPPED,
                        measure=measure.number,
                        message=f"The ornament {source_note.ornament} is not imported.",
                    )
                )

        by_carrier[carrier_id] = (articulations, ornament, measure.number)

    def _octave_item(
        self,
        *,
        document: ScoreDocument,
        staff_number: int,
        start: Place,
        end: tuple[int, MeasurePosition] | None,
        octaves: int,
        number: str,
        lengths: list[Fraction],
        starts: list[Fraction],
        to_the_end: list[tuple[int, Fraction]],
    ) -> _Item | None:
        """An octave line; one that lasts to the end of the score is made to end inside the last
        measure and opened afterwards, since no place stands for the end of the score."""
        begin: tuple[int, MeasurePosition] | None = _locate(place=start, lengths=lengths)
        if begin is None:
            return None

        if end is None:
            last: int = len(document.measures) - 1
            inside: Fraction = (
                Fraction(0)
                if begin[0] < last
                else (begin[1].value + lengths[last] / _QUARTERS_PER_WHOLE) / 2
            )
            end = (last, _position_of(whole_notes=inside))
            to_the_end.append((staff_number - 1, starts[begin[0]] + begin[1].value))

        return _Item(
            measure=number,
            what="An octave line",
            intent=CreateOctaveTranspositionIntent(
                staff_id=document.staffs[staff_number - 1].id,
                start_measure_id=document.measures[begin[0]].id,
                start_position=begin[1],
                end_measure_id=document.measures[end[0]].id,
                end_position=end[1],
                octaves=octaves,
                mode=PitchEditMode.PRESERVE_STEP,
            ),
        )

    def _open_to_the_end(
        self,
        *,
        document: ScoreDocument,
        lines: list[tuple[int, Fraction]],
        issues: list[ImportIssue],
    ) -> None:
        """Makes the octave lines that were set to end inside the last measure last until the end
        of the score. ``lines`` hold the staff index and where the line starts in the score."""
        if not lines:
            return

        geometry: ScoreGeometry = ScoreGeometry(document=document)
        contexts: ContextIndex = ContextIndex(document=document, geometry=geometry)
        starts: list[Fraction] = _starts(document=document)
        items: list[_Item] = []
        for context in contexts.contexts():
            if not isinstance(context, OctaveTransposition):
                continue

            place: Fraction = (
                starts[document.measures.index(context.start.measure)]
                + context.start.position.value
            )
            if (document.staffs.index(context.staff), place) in lines:
                items.append(
                    _Item(
                        measure="",
                        what="An octave line",
                        intent=OpenContextEndIntent(
                            context_ids=(context.id,), mode=PitchEditMode.PRESERVE_STEP
                        ),
                    )
                )

        self._run(document=document, items=items, issues=issues)

    def _dynamics(
        self,
        *,
        document: ScoreDocument,
        source: SourceScore,
        lengths: list[Fraction],
        issues: list[ImportIssue],
    ) -> list[_Dynamic]:
        """The dynamics of the file in order. At a place the file puts one on the staves, it is the
        piece's; where it puts different ones on the two, each is its staff's."""
        at: dict[Place, dict[int, DynamicMarking]] = {}
        for index, measure in enumerate(source.measures):
            for dynamic in sorted(measure.dynamics, key=lambda d: d.onset):
                marking: DynamicMarking | None = _marking_of(dynamic=dynamic)
                if marking is None:
                    issues.append(
                        ImportIssue(
                            kind=IssueKind.SKIPPED,
                            measure=measure.number,
                            message=f"The dynamic {dynamic.marking} is not imported.",
                        )
                    )
                    continue

                on_staffs: dict[int, DynamicMarking] = at.setdefault((index, dynamic.onset), {})
                if dynamic.staff in on_staffs:
                    if on_staffs[dynamic.staff] is not marking:
                        issues.append(
                            ImportIssue(
                                kind=IssueKind.SKIPPED,
                                measure=measure.number,
                                message="Two dynamics at one place: only the first is imported.",
                            )
                        )
                    continue

                on_staffs[dynamic.staff] = marking

        found: list[_Dynamic] = []
        for place, on_staffs in at.items():
            if len(set(on_staffs.values())) == 1:
                found.append(
                    _Dynamic(place=place, marking=next(iter(on_staffs.values())), staff=None)
                )
            else:
                found.extend(
                    _Dynamic(place=place, marking=marking, staff=staff)
                    for staff, marking in sorted(on_staffs.items())
                )

        return found

    def _dynamic_items(
        self,
        *,
        document: ScoreDocument,
        dynamics: list[_Dynamic],
        voices_on: Callable[[int, Place], tuple[str, ...]],
        source: SourceScore,
        lengths: list[Fraction],
    ) -> list[_Item]:
        items: list[_Item] = []
        for dynamic in dynamics:
            where: tuple[int, MeasurePosition] | None = _locate(
                place=dynamic.place, lengths=lengths
            )
            if where is None:
                continue

            voice_ids: tuple[str, ...] = (
                voices_on(dynamic.staff, dynamic.place) if dynamic.staff is not None else ()
            ) or tuple(voice.id for voice in document.voices)
            items.append(
                _Item(
                    measure=source.measures[dynamic.place[0]].number,
                    what=f"The dynamic {dynamic.marking.value}",
                    intent=SetDynamicIntent(
                        measure_id=document.measures[where[0]].id,
                        position=where[1],
                        voice_ids=voice_ids,
                        dynamic=dynamic.marking,
                    ),
                )
            )

        return items

    def _tempo_items(
        self,
        *,
        document: ScoreDocument,
        source: SourceScore,
        lengths: list[Fraction],
        issues: list[ImportIssue],
    ) -> list[_Item]:
        items: list[_Item] = []
        taken: set[Place] = set()
        for index, measure in enumerate(source.measures):
            for tempo in sorted(measure.tempos, key=lambda t: t.onset):
                where: tuple[int, MeasurePosition] | None = _locate(
                    place=(index, tempo.onset), lengths=lengths
                )
                kind: str = tempo.beat_type or "quarter"
                if kind not in NOTE_TYPES or where is None:
                    issues.append(
                        ImportIssue(
                            kind=IssueKind.SKIPPED,
                            measure=measure.number,
                            message=f"A tempo counted in {kind} notes is not imported.",
                        )
                    )
                    continue

                if (index, tempo.onset) in taken:
                    continue

                taken.add((index, tempo.onset))
                items.append(
                    _Item(
                        measure=measure.number,
                        what="A tempo",
                        intent=SetTempoIntent(
                            measure_id=document.measures[where[0]].id,
                            position=where[1],
                            beat=DottedRhythmicValue(value=NOTE_TYPES[kind], dots_count=tempo.dots),
                            bpm=tempo.bpm,
                        ),
                    )
                )

        return items

    def _hairpin_items(
        self,
        *,
        document: ScoreDocument,
        source: SourceScore,
        dynamics: list[_Dynamic],
        voices_on: Callable[[int, Place], tuple[str, ...]],
        lengths: list[Fraction],
        issues: list[ImportIssue],
    ) -> list[_Item]:
        """A hairpin goes to the next dynamic after its end (the engine states a hairpin by the
        level it reaches). One with a dynamic inside it, with none to reach, or that would not
        change the level the right way, is left out. Each staff has its own hairpins and the
        dynamics that are its own or the piece's; a hairpin is for the voices of its staff only
        where a hairpin of the other staff runs over the same time or the staffs are not at the
        same level, and for all voices otherwise; a hairpin is made for each voice named."""
        spans_of: dict[int, list[tuple[Place, Place, str]]] = {}
        open_wedges: dict[int, tuple[Place, str]] = {}
        for index, measure in enumerate(source.measures):
            for wedge in sorted(measure.wedges, key=lambda w: w.onset):
                place: Place = (index, wedge.onset)
                spans: list[tuple[Place, Place, str]] = spans_of.setdefault(wedge.staff, [])
                if wedge.staff in open_wedges:
                    spans.append((open_wedges[wedge.staff][0], place, open_wedges[wedge.staff][1]))
                    del open_wedges[wedge.staff]

                if wedge.kind in ("crescendo", "diminuendo"):
                    open_wedges[wedge.staff] = (place, wedge.kind)

        levels_of: dict[int, list[tuple[Place, DynamicMarking]]] = {
            staff: [
                (dynamic.place, dynamic.marking)
                for dynamic in dynamics
                if dynamic.staff is None or dynamic.staff == staff
            ]
            for staff in {note.staff for measure in source.measures for note in measure.notes}
        }
        items: list[_Item] = []
        for staff, spans in spans_of.items():
            levels: list[tuple[Place, DynamicMarking]] = levels_of.get(staff, [])
            reached: list[tuple[Place, DynamicMarking]] = []
            for number, (start, stop, kind) in enumerate(spans):
                label: str = source.measures[start[0]].number
                following: Place | None = spans[number + 1][0] if number + 1 < len(spans) else None
                target: DynamicMarking | None = None
                problem: str | None = None
                if any(start < place < stop for place, _ in levels):
                    problem = "has a dynamic inside it"
                else:
                    for place, marking in levels:
                        if place >= stop:
                            if following is None or place <= following:
                                target = marking

                            break

                    if target is None:
                        problem = "has no dynamic after it to reach"

                where_start: tuple[int, MeasurePosition] | None = _locate(
                    place=start, lengths=lengths
                )
                where_stop: tuple[int, MeasurePosition] | None = _locate(
                    place=stop, lengths=lengths
                ) or self._last_place(document=document, after=start, lengths=lengths)
                if problem is None and (where_start is None or where_stop is None):
                    problem = "has no place to end"

                if problem is None and target is not None:
                    before: DynamicMarking = _level_at(
                        place=start, dynamics=levels, reached=reached
                    )
                    steps: int = target.level - before.level
                    if steps == 0 or (steps > 0) != (kind == "crescendo"):
                        direction: str = "rise" if kind == "crescendo" else "fall"
                        problem = f"does not {direction} to {target.value}"

                if (
                    problem is not None
                    or target is None
                    or where_start is None
                    or where_stop is None
                ):
                    issues.append(
                        ImportIssue(
                            kind=IssueKind.SKIPPED,
                            measure=label,
                            message=f"A {kind} hairpin that {problem} is not imported.",
                        )
                    )
                    continue

                reached.append((stop, target))
                shared: bool = any(
                    other != staff
                    and any(
                        other_start < stop and start < other_stop
                        for other_start, other_stop, _ in other_spans
                    )
                    for other, other_spans in spans_of.items()
                ) or any(
                    _level_at(place=start, dynamics=other_levels, reached=[]) is not before
                    for other, other_levels in levels_of.items()
                    if other != staff
                )
                items.append(
                    _Item(
                        measure=label,
                        what="A hairpin",
                        intent=CreateHairpinIntent(
                            start_measure_id=document.measures[where_start[0]].id,
                            start_position=where_start[1],
                            end_measure_id=document.measures[where_stop[0]].id,
                            end_position=where_stop[1],
                            voice_ids=(voices_on(staff, start) if shared else ())
                            or tuple(voice.id for voice in document.voices),
                            target=target,
                        ),
                    )
                )

        for place, kind in open_wedges.values():
            issues.append(
                ImportIssue(
                    kind=IssueKind.SKIPPED,
                    measure=source.measures[place[0]].number,
                    message=f"A {kind} hairpin that never ends is not imported.",
                )
            )

        return items

    def _slur_items(
        self,
        *,
        document: ScoreDocument,
        source: SourceScore,
        voice_numbers: list[int],
        lengths: list[Fraction],
        issues: list[ImportIssue],
    ) -> list[_Item]:
        items: list[_Item] = []
        open_slurs: dict[tuple[int, int], Place] = {}
        for index, measure in enumerate(source.measures):
            for slur in sorted(measure.slurs, key=lambda s: s.onset):
                line: tuple[int, int] = (slur.voice, slur.number)
                place: Place = (index, slur.onset)
                if slur.kind == "start":
                    open_slurs[line] = place
                    continue

                start: Place | None = open_slurs.pop(line, None)
                where_start: tuple[int, MeasurePosition] | None = (
                    None if start is None else _locate(place=start, lengths=lengths)
                )
                where_stop: tuple[int, MeasurePosition] | None = _locate(
                    place=place, lengths=lengths
                )
                if (
                    start is None
                    or where_start is None
                    or where_stop is None
                    or slur.voice not in voice_numbers
                    or start >= place
                ):
                    issues.append(
                        ImportIssue(
                            kind=IssueKind.SKIPPED,
                            measure=measure.number,
                            message="A slur that does not run from one note to a later one "
                            "is not imported.",
                        )
                    )
                    continue

                items.append(
                    _Item(
                        measure=source.measures[start[0]].number,
                        what="A slur",
                        intent=CreateSlurIntent(
                            start_measure_id=document.measures[where_start[0]].id,
                            start_position=where_start[1],
                            end_measure_id=document.measures[where_stop[0]].id,
                            end_position=where_stop[1],
                            voice_ids=(document.voices[voice_numbers.index(slur.voice)].id,),
                        ),
                    )
                )

        for place in open_slurs.values():
            issues.append(
                ImportIssue(
                    kind=IssueKind.SKIPPED,
                    measure=source.measures[place[0]].number,
                    message="A slur that never ends is not imported.",
                )
            )

        return items

    def _pedal_items(
        self,
        *,
        document: ScoreDocument,
        source: SourceScore,
        lengths: list[Fraction],
        issues: list[ImportIssue],
    ) -> list[_Item]:
        """The damper pedal as stretches held down; one never let up ends at the last place of the
        score with a note."""
        stretches: list[tuple[Place, Place | None]] = []
        down: Place | None = None
        for index, measure in enumerate(source.measures):
            for pedal in sorted(measure.pedals, key=lambda p: p.onset):
                place: Place = (index, pedal.onset)
                if pedal.kind in ("stop", "change") and down is not None:
                    stretches.append((down, place))
                    down = None

                if pedal.kind in ("start", "change") and down is None:
                    down = place

        if down is not None:
            stretches.append((down, None))

        items: list[_Item] = []
        for start, stop in stretches:
            where_start: tuple[int, MeasurePosition] | None = _locate(place=start, lengths=lengths)
            where_stop: tuple[int, MeasurePosition] | None = (
                None if stop is None else _locate(place=stop, lengths=lengths)
            ) or self._last_place(document=document, after=start, lengths=lengths)
            if where_start is None or where_stop is None or (stop is not None and stop <= start):
                issues.append(
                    ImportIssue(
                        kind=IssueKind.SKIPPED,
                        measure=source.measures[start[0]].number,
                        message="A pedal that has no place to end is not imported.",
                    )
                )
                continue

            items.append(
                _Item(
                    measure=source.measures[start[0]].number,
                    what="A pedal",
                    intent=CreateSustainHoldIntent(
                        start_measure_id=document.measures[where_start[0]].id,
                        start_position=where_start[1],
                        end_measure_id=document.measures[where_stop[0]].id,
                        end_position=where_stop[1],
                    ),
                )
            )

        return items

    def _repeat_items(
        self,
        *,
        document: ScoreDocument,
        source: SourceScore,
        lengths: list[Fraction],
        issues: list[ImportIssue],
    ) -> list[_Item]:
        """Repeats and endings. A repeat starts at a forward sign, or where the score starts, or
        after the repeat before it; it ends at a backward sign. Endings that follow one another
        make one volta with the stretch before them as its body."""
        endings: dict[int, _Ending] = _endings(measures=source.measures, issues=issues)
        items: list[_Item] = []
        start: int = 0
        index: int = 0
        count: int = len(source.measures)
        while index < count:
            measure: SourceMeasure = source.measures[index]
            if _barline(measure=measure, location="left", repeat="forward") is not None:
                start = index

            if index in endings:
                group: list[_Ending] = [endings[index]]
                while group[-1].last + 1 in endings and group[-1].closes_repeat:
                    group.append(endings[group[-1].last + 1])

                volta: _Item | None = self._volta_item(
                    document=document,
                    source=source,
                    start=start,
                    group=group,
                    lengths=lengths,
                    issues=issues,
                )
                if volta is not None:
                    items.append(volta)

                index = group[-1].last + 1
                start = index
                continue

            backward: SourceBarline | None = _barline(
                measure=measure, location="right", repeat="backward"
            )
            if backward is not None:
                begin: tuple[int, MeasurePosition] | None = _locate(
                    place=(start, Fraction(0)), lengths=lengths
                )
                end: tuple[int, MeasurePosition] | None = _locate(
                    place=(index, lengths[index] * _QUARTERS_PER_WHOLE), lengths=lengths
                )
                if begin is not None:
                    items.append(
                        _Item(
                            measure=measure.number,
                            what="A repeat",
                            intent=CreateRefrainIntent(
                                start_measure_id=document.measures[begin[0]].id,
                                start_position=begin[1],
                                end_measure_id=None
                                if end is None
                                else document.measures[end[0]].id,
                                end_position=None if end is None else end[1],
                                times=backward.times or _DEFAULT_REPEAT_TIMES,
                            ),
                        )
                    )

                start = index + 1

            index += 1

        return items

    def _volta_item(
        self,
        *,
        document: ScoreDocument,
        source: SourceScore,
        start: int,
        group: list[_Ending],
        lengths: list[Fraction],
        issues: list[ImportIssue],
    ) -> _Item | None:
        begin: tuple[int, MeasurePosition] | None = _locate(
            place=(start, Fraction(0)), lengths=lengths
        )
        fragments: list[VoltaFragmentIntent] = []
        # The last ending, when no repeat sign follows it, is the pass that goes on: the volta
        # does not store it.
        stored: list[_Ending] = group if group[-1].closes_repeat else group[:-1]
        for ending in stored:
            end: tuple[int, MeasurePosition] | None = _locate(
                place=(ending.last, lengths[ending.last] * _QUARTERS_PER_WHOLE), lengths=lengths
            )
            fragments.append(
                VoltaFragmentIntent(
                    end_measure_id=None if end is None else document.measures[end[0]].id,
                    end_position=None if end is None else end[1],
                    passes=ending.passes,
                )
            )

        body_end: tuple[int, MeasurePosition] | None = _locate(
            place=(group[0].first, Fraction(0)), lengths=lengths
        )
        if (
            not fragments
            or begin is None
            or body_end is None
            or (begin[0], begin[1].value)
            >= (
                body_end[0],
                body_end[1].value,
            )
        ):
            issues.append(
                ImportIssue(
                    kind=IssueKind.SKIPPED,
                    measure=source.measures[group[0].first].number,
                    message="Endings with nothing before them to repeat are not imported.",
                )
            )
            return None

        return _Item(
            measure=source.measures[group[0].first].number,
            what="Endings of a repeat",
            intent=CreateVoltaIntent(
                start_measure_id=document.measures[begin[0]].id,
                start_position=begin[1],
                body_end_measure_id=document.measures[body_end[0]].id,
                body_end_position=body_end[1],
                fragments=tuple(fragments),
            ),
        )

    def _last_place(
        self, *, document: ScoreDocument, after: Place, lengths: list[Fraction]
    ) -> tuple[int, MeasurePosition] | None:
        """The last place of the score where something starts, if it is later than ``after``."""
        last: int = len(document.measures) - 1
        positions: list[MeasurePosition] = [
            anchor.position for anchor in document.measures[last].anchors
        ]
        if not positions:
            return None

        latest: MeasurePosition = max(positions, key=lambda position: position.value)
        if (last, latest.value * _QUARTERS_PER_WHOLE) <= after:
            return None

        return last, latest

    def _run(
        self, *, document: ScoreDocument, items: Sequence[_Item], issues: list[ImportIssue]
    ) -> None:
        """Puts the items in as one pass; when it is refused, each item as a pass of its own, so
        only the refused ones are left out."""
        if not items:
            return

        try:
            with self._engine.transaction(document=document) as transaction:
                transaction.run(
                    requests=[
                        request
                        for item in items
                        for request in self._compiler.compile(
                            document=document, intent=item.intent, entities=transaction.entities
                        )
                    ]
                )
            return
        except MutationRejectedError:
            pass

        for item in items:
            for intent in item.parts or (item.intent,):
                try:
                    with self._engine.transaction(document=document) as transaction:
                        transaction.run(
                            requests=self._compiler.compile(
                                document=document, intent=intent, entities=transaction.entities
                            )
                        )
                except MutationRejectedError as error:
                    issues.append(
                        ImportIssue(
                            kind=IssueKind.SKIPPED,
                            measure=item.measure,
                            message=f"{item.what} is not imported: {error}",
                        )
                    )


def _lengths(*, document: ScoreDocument) -> list[Fraction]:
    """How long each measure is, in whole notes."""
    return [measure.time_signature.fraction for measure in document.measures]


def _starts(*, document: ScoreDocument) -> list[Fraction]:
    """Where each measure starts in the score, in whole notes."""
    starts: list[Fraction] = []
    offset: Fraction = Fraction(0)
    for length in _lengths(document=document):
        starts.append(offset)
        offset += length

    return starts


def _position_of(*, whole_notes: Fraction) -> MeasurePosition:
    return MeasurePosition.of(numerator=whole_notes.numerator, denominator=whole_notes.denominator)


def _locate(*, place: Place, lengths: list[Fraction]) -> tuple[int, MeasurePosition] | None:
    """The place as the score names it: the measure and a position inside it. What lies at the end
    of a measure or past it is the start of the next measure; at the end of the score there is
    no such place."""
    index, quarters = place
    whole_notes: Fraction = quarters / _QUARTERS_PER_WHOLE
    if whole_notes >= lengths[index]:
        index += 1
        whole_notes = Fraction(0)
        if index == len(lengths):
            return None

    return index, _position_of(whole_notes=whole_notes)


def _marking_of(*, dynamic: SourceDynamic) -> DynamicMarking | None:
    try:
        return DynamicMarking(dynamic.marking)
    except ValueError:
        return None


def _level_at(
    *,
    place: Place,
    dynamics: list[tuple[Place, DynamicMarking]],
    reached: list[tuple[Place, DynamicMarking]],
) -> DynamicMarking:
    """The dynamic in force at ``place``: the last one the file sets there or before, or the level
    a hairpin before it reached."""
    level: DynamicMarking = _INITIAL_DYNAMIC
    since: Place | None = None
    for where, marking in [*dynamics, *reached]:
        if where <= place and (since is None or where >= since):
            level = marking
            since = where

    return level


def _barline(*, measure: SourceMeasure, location: str, repeat: str) -> SourceBarline | None:
    for barline in measure.barlines:
        if barline.location == location and barline.repeat == repeat:
            return barline

    return None


def _endings(
    *, measures: tuple[SourceMeasure, ...], issues: list[ImportIssue]
) -> dict[int, _Ending]:
    """The endings of repeats by the measure each starts in."""
    found: dict[int, _Ending] = {}
    for index, measure in enumerate(measures):
        for barline in measure.barlines:
            if barline.location != "left" or barline.ending_kind != "start":
                continue

            passes: tuple[int, ...] = _passes_of(text=barline.ending_number)
            if not passes:
                issues.append(
                    ImportIssue(
                        kind=IssueKind.SKIPPED,
                        measure=measure.number,
                        message="An ending without a number of its pass is not imported.",
                    )
                )
                continue

            last: int = index
            closing: SourceBarline | None = None
            for follow in range(index, len(measures)):
                if follow > index and any(
                    b.location == "left" and b.ending_kind == "start"
                    for b in measures[follow].barlines
                ):
                    break

                last = follow
                closing = next(
                    (
                        b
                        for b in measures[follow].barlines
                        if b.location == "right" and b.ending_kind in ("stop", "discontinue")
                    ),
                    None,
                )
                if closing is not None:
                    break

            backward: SourceBarline | None = _barline(
                measure=measures[last], location="right", repeat="backward"
            )
            found[index] = _Ending(
                first=index,
                last=last,
                passes=passes,
                closes_repeat=backward is not None,
                times=None if backward is None else backward.times,
            )

    return found


def _passes_of(*, text: str | None) -> tuple[int, ...]:
    """The passes an ending names: ``"1"``, ``"1, 2"`` or ``"1-3"``."""
    passes: list[int] = []
    for part in (text or "").replace(" ", "").split(","):
        low, _, high = part.partition("-")
        if low.isdigit() and (not high or high.isdigit()):
            passes.extend(range(int(low), int(high or low) + 1))

    return tuple(passes)
