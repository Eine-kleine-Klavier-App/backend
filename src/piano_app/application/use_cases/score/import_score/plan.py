from dataclasses import dataclass
from fractions import Fraction
from math import gcd

from piano_app.application.ports.importing import ImportIssue, IssueKind, SourceNote, SourceScore
from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    GracePlacement,
    RhythmicSize,
    RhythmicValue,
)
from piano_app.domain.score.document.models.notation.stem import StemDirection

from .lookup import LeafKey
from .mappings import NOTE_TYPES, accidental_of, midi_of

STAFF_COUNT: int = 2

_QUARTERS_PER_WHOLE: int = 4


@dataclass(frozen=True, slots=True, kw_only=True)
class TupletLead:
    """On the first element of a tuplet: the sizes the tuplet is made with."""

    written: RhythmicSize
    occupied: RhythmicSize


@dataclass(frozen=True, slots=True, kw_only=True)
class Entry:
    """One note or rest to put in."""

    measure_index: int
    note: SourceNote
    value: DottedRhythmicValue
    voice_index: int
    accidental: Accidental | None
    """``None`` for a rest."""

    rank: int
    """Its place in a chord: 0 for the first note, a rest or a note alone."""

    layer: int
    """The pass it goes in: later than the note or tuplet it depends on."""

    tuplet: TupletLead | None


@dataclass(frozen=True, slots=True, kw_only=True)
class TiePair:
    start: tuple[int, int, int, Fraction, int]
    end: tuple[int, int, int, Fraction, int]
    """Voice, staff, measure, position in whole notes and MIDI number of each note."""


@dataclass(frozen=True, slots=True, kw_only=True)
class GraceEntry:
    host_voice: int
    host_measure: int
    host_position: Fraction
    """Where the note the grace note belongs to stands, in whole notes from its measure start."""

    placement: GracePlacement
    note: SourceNote
    value: DottedRhythmicValue
    accidental: Accidental
    item_index: int
    """Which grace item of the group this note belongs to (a chord is one item)."""

    is_lead: bool
    """The first note of its item."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Plan:
    layers: dict[int, list[Entry]]
    ties: list[TiePair]
    graces: dict[int, list[GraceEntry]]
    """By the pass they go in."""

    beams: list[tuple[LeafKey, ...]]
    """The runs of notes the file beams together, each by the place of its notes in time order."""

    stems: list[tuple[LeafKey, StemDirection]]
    """The direction the file draws the stem of each note or chord with."""


@dataclass(kw_only=True)
class _Draft:
    measure_index: int
    note: SourceNote
    value: DottedRhythmicValue
    voice_index: int
    accidental: Accidental | None
    rank: int
    end: Fraction
    group_lead: bool = False
    inner: bool = False
    tuplet: TupletLead | None = None


def _end_of(*, entry: Entry) -> Fraction:
    """Where the note or rest ends, in quarter notes from the start of its measure."""
    note: SourceNote = entry.note
    return note.onset + (
        note.duration if note.tuplet is not None else entry.value.fraction * _QUARTERS_PER_WHOLE
    )


def _gcd(left: Fraction, right: Fraction) -> Fraction:
    """The largest fraction both are a whole number of (0 stands for none yet)."""
    if left == 0:
        return right

    common: int = gcd(left.numerator * right.denominator, right.numerator * left.denominator)

    return Fraction(common, left.denominator * right.denominator)


class ScorePlanner:
    """Decides what of the source score goes in, and in which pass, before any of it is built.

    The notes and rests are laid out by their place in a chord and in a tuplet (a note is compiled
    against the score as the pass before it left it, so a second note of a chord and a note inside
    a tuplet wait for the one they join). What the score cannot take is left out here and goes into
    the issues.
    """

    def plan(
        self,
        *,
        document: ScoreDocument,
        source: SourceScore,
        voice_numbers: list[int],
        issues: list[ImportIssue],
    ) -> Plan:
        drafts: list[_Draft] = []
        graces: list[tuple[int, SourceNote, int, DottedRhythmicValue, Accidental]] = []

        for index, source_measure in enumerate(source.measures):
            length: Fraction = (
                document.measures[index].time_signature.fraction * _QUARTERS_PER_WHOLE
            )
            ranks: dict[tuple[int, Fraction], int] = {}
            leads: dict[tuple[int, Fraction], tuple[Fraction, bool]] = {}
            intervals: dict[int, list[tuple[Fraction, Fraction]]] = {}

            for note in source_measure.notes:
                if note.is_measure_rest:
                    continue

                parts: tuple[DottedRhythmicValue, Accidental | None, int, Fraction] | None = (
                    self._accept(
                        note=note,
                        length=length,
                        voice_numbers=voice_numbers,
                        number=source_measure.number,
                        issues=issues,
                    )
                )
                if parts is None:
                    continue

                value, accidental, voice_index, end = parts
                if note.is_grace:
                    if accidental is None:
                        issues.append(
                            ImportIssue(
                                kind=IssueKind.SKIPPED,
                                measure=source_measure.number,
                                message="A grace rest is not imported.",
                            )
                        )
                    else:
                        graces.append((index, note, voice_index, value, accidental))

                    continue

                rank: int | None = self._rank_of(
                    key=(voice_index, note.onset),
                    voice_index=voice_index,
                    onset=note.onset,
                    end=end,
                    is_pitched=accidental is not None,
                    ranks=ranks,
                    leads=leads,
                    intervals=intervals,
                )
                if rank is None:
                    issues.append(
                        ImportIssue(
                            kind=IssueKind.SKIPPED,
                            measure=source_measure.number,
                            message="A note or rest that overlaps another one in its voice "
                            "is not imported.",
                        )
                    )
                    continue

                drafts.append(
                    _Draft(
                        measure_index=index,
                        note=note,
                        value=value,
                        voice_index=voice_index,
                        accidental=accidental,
                        rank=rank,
                        end=end,
                    )
                )

        kept: list[_Draft] = self._group_tuplets(drafts=drafts, source=source, issues=issues)
        entries: list[Entry] = [
            Entry(
                measure_index=draft.measure_index,
                note=draft.note,
                value=draft.value,
                voice_index=draft.voice_index,
                accidental=draft.accidental,
                rank=draft.rank,
                layer=draft.rank + (1 if draft.inner else 0),
                tuplet=draft.tuplet,
            )
            for draft in kept
        ]
        layers: dict[int, list[Entry]] = {}
        for entry in entries:
            layers.setdefault(entry.layer, []).append(entry)

        return Plan(
            layers=layers,
            ties=self._ties(entries=entries, source=source, issues=issues),
            graces=self._graces(graces=graces, entries=entries, source=source, issues=issues),
            beams=self._beams(entries=entries),
            stems=self._stems(entries=entries),
        )

    def _accept(
        self,
        *,
        note: SourceNote,
        length: Fraction,
        voice_numbers: list[int],
        number: str,
        issues: list[ImportIssue],
    ) -> tuple[DottedRhythmicValue, Accidental | None, int, Fraction] | None:
        """The written value, the accidental (``None`` for a rest), the voice and where the note
        ends; ``None`` when it cannot go in."""
        reason: str | None = None
        value: DottedRhythmicValue | None = None
        accidental: Accidental | None = None

        if note.written_type not in NOTE_TYPES:
            reason = f"A {note.written_type or 'timeless'} note value is not imported."
        elif not 1 <= note.staff <= STAFF_COUNT:
            reason = f"Staff {note.staff} is not imported."
        else:
            try:
                value = DottedRhythmicValue(
                    value=NOTE_TYPES[note.written_type], dots_count=note.dots
                )
            except ValueError:
                reason = "A note with that many dots is not imported."

            if note.pitch is not None:
                accidental = accidental_of(pitch=note.pitch)
                if accidental is None:
                    reason = "A note with that accidental is not imported."

        end: Fraction = note.onset
        if reason is None and value is not None:
            written: Fraction = value.fraction * _QUARTERS_PER_WHOLE
            end = note.onset + (note.duration if note.tuplet is not None else written)
            if note.is_grace:
                end = note.onset
            elif end > length:
                reason = "A note that reaches past the end of its measure is not imported."
            elif note.tuplet is None and written != note.duration:
                issues.append(
                    ImportIssue(
                        kind=IssueKind.CHANGED,
                        measure=number,
                        message="A note whose length differs from its notation got the "
                        "notated length.",
                    )
                )

        if reason is not None or value is None:
            issues.append(ImportIssue(kind=IssueKind.SKIPPED, measure=number, message=reason or ""))
            return None

        return value, accidental, voice_numbers.index(note.voice), end

    def _rank_of(
        self,
        *,
        key: tuple[int, Fraction],
        voice_index: int,
        onset: Fraction,
        end: Fraction,
        is_pitched: bool,
        ranks: dict[tuple[int, Fraction], int],
        leads: dict[tuple[int, Fraction], tuple[Fraction, bool]],
        intervals: dict[int, list[tuple[Fraction, Fraction]]],
    ) -> int | None:
        """Its place in a chord, or ``None`` when it cannot go in."""
        if key in leads:
            lead_end, lead_is_pitched = leads[key]
            if not (is_pitched and lead_is_pitched and end == lead_end):
                return None

            ranks[key] += 1
            return ranks[key]

        for start, stop in intervals.get(voice_index, []):
            if onset < stop and start < end:
                return None

        intervals.setdefault(voice_index, []).append((onset, end))
        leads[key] = (end, is_pitched)
        ranks[key] = 0

        return 0

    def _group_tuplets(
        self,
        *,
        drafts: list[_Draft],
        source: SourceScore,
        issues: list[ImportIssue],
    ) -> list[_Draft]:
        """Marks the first element of each tuplet and the elements inside it. A run of elements
        of one ratio is cut into tuplets of the actual number of units (the unit is the largest
        note value that every element of the run is a whole number of). A tuplet that is not whole,
        or that no unit measures, is left out."""
        dropped: set[int] = set()
        runs: dict[tuple[int, int], list[_Draft]] = {}
        for draft in drafts:
            if draft.note.tuplet is not None and draft.rank == 0:
                runs.setdefault((draft.measure_index, draft.voice_index), []).append(draft)

        for (measure_index, _), run in runs.items():
            number: str = source.measures[measure_index].number
            run.sort(key=lambda draft: draft.note.onset)
            for segment in self._segments(run=run):
                self._group_segment(segment=segment, number=number, dropped=dropped, issues=issues)

        # a chord member follows its lead into the tuplet or out of it
        by_place: dict[tuple[int, int, Fraction], _Draft] = {
            (draft.measure_index, draft.voice_index, draft.note.onset): draft
            for draft in drafts
            if draft.rank == 0
        }
        for draft in drafts:
            if draft.rank > 0:
                lead: _Draft = by_place[(draft.measure_index, draft.voice_index, draft.note.onset)]
                draft.inner = lead.inner
                if id(lead) in dropped:
                    dropped.add(id(draft))

        return [draft for draft in drafts if id(draft) not in dropped]

    def _segments(self, *, run: list[_Draft]) -> list[list[_Draft]]:
        """The parts of a run that follow one another in time and share one ratio."""
        segments: list[list[_Draft]] = []
        for draft in run:
            if segments and (
                segments[-1][-1].end == draft.note.onset
                and segments[-1][-1].note.tuplet == draft.note.tuplet
            ):
                segments[-1].append(draft)
            else:
                segments.append([draft])

        return segments

    def _group_segment(
        self,
        *,
        segment: list[_Draft],
        number: str,
        dropped: set[int],
        issues: list[ImportIssue],
    ) -> None:
        actual, normal = segment[0].note.tuplet or (0, 0)
        unit: Fraction = Fraction(0)
        for draft in segment:
            unit = _gcd(unit, draft.value.fraction)

        value: RhythmicValue | None = next(
            (candidate for candidate in RhythmicValue if candidate.fraction == unit), None
        )
        if value is None or normal == actual:
            for draft in segment:
                dropped.add(id(draft))

            issues.append(
                ImportIssue(
                    kind=IssueKind.SKIPPED,
                    measure=number,
                    message="A tuplet this irregular is not imported.",
                )
            )
            return

        unit_value: DottedRhythmicValue = DottedRhythmicValue(value=value)
        group: list[_Draft] = []
        total: int = 0
        members: list[_Draft | None] = [*segment, None]
        for member in members:
            units: int = int(member.value.fraction / unit) if member is not None else 0
            if group and (member is None or total + units > actual):
                self._close_group(
                    group=group,
                    unit=unit_value,
                    actual=actual,
                    normal=normal,
                    complete=total == actual,
                    number=number,
                    dropped=dropped,
                    issues=issues,
                )
                group = []
                total = 0

            if member is not None:
                group.append(member)
                total += units

    def _close_group(
        self,
        *,
        group: list[_Draft],
        unit: DottedRhythmicValue,
        actual: int,
        normal: int,
        complete: bool,
        number: str,
        dropped: set[int],
        issues: list[ImportIssue],
    ) -> None:
        if not complete:
            for member in group:
                dropped.add(id(member))

            issues.append(
                ImportIssue(
                    kind=IssueKind.SKIPPED,
                    measure=number,
                    message="A tuplet that is not whole is not imported.",
                )
            )
            return

        group[0].group_lead = True
        group[0].tuplet = TupletLead(
            written=RhythmicSize(value=unit, count=actual),
            occupied=RhythmicSize(value=unit, count=normal),
        )
        for member in group[1:]:
            member.inner = True

    def _beams(self, *, entries: list[Entry]) -> list[tuple[LeafKey, ...]]:
        """The beams of the file: a run of notes from the one that begins a beam to the one that
        ends it, in one voice, each starting where the one before ends. A note of a quarter or
        longer, or a gap, cuts a run, as the engine keeps a beam only on short neighbours; a run of
        one note is no beam."""
        leads: list[Entry] = sorted(
            (
                entry
                for entry in entries
                if entry.rank == 0 and entry.note.pitch is not None and entry.note.beam is not None
            ),
            key=lambda entry: (entry.voice_index, entry.measure_index, entry.note.onset),
        )
        runs: list[list[Entry]] = []
        current: list[Entry] = []
        for entry in leads:
            joins: bool = (
                entry.note.beam != "begin"
                and bool(current)
                and current[-1].voice_index == entry.voice_index
                and current[-1].measure_index == entry.measure_index
                and _end_of(entry=current[-1]) == entry.note.onset
            )
            if not joins:
                runs.append(current)
                current = []

            if entry.value.value <= RhythmicValue.QUARTER:
                runs.append(current)
                current = []
                continue

            # a note that begins a beam, joins one, or follows a cut starts or goes on with a run
            current.append(entry)
            if entry.note.beam == "end":
                runs.append(current)
                current = []

        runs.append(current)

        return [
            tuple(
                (entry.voice_index, entry.measure_index, entry.note.onset / _QUARTERS_PER_WHOLE)
                for entry in run
            )
            for run in runs
            if len(run) >= 2
        ]

    def _stems(self, *, entries: list[Entry]) -> list[tuple[LeafKey, StemDirection]]:
        return [
            (
                (entry.voice_index, entry.measure_index, entry.note.onset / _QUARTERS_PER_WHOLE),
                StemDirection(entry.note.stem),
            )
            for entry in entries
            if entry.rank == 0 and entry.note.pitch is not None and entry.note.stem is not None
        ]

    def _ties(
        self, *, entries: list[Entry], source: SourceScore, issues: list[ImportIssue]
    ) -> list[TiePair]:
        pairs: list[TiePair] = []
        pending: dict[tuple[int, int, int], tuple[int, int, int, Fraction, int]] = {}
        ordered: list[Entry] = sorted(
            (entry for entry in entries if entry.note.pitch is not None),
            key=lambda entry: (entry.measure_index, entry.note.onset),
        )
        for entry in ordered:
            pitch = entry.note.pitch
            if pitch is None:
                continue

            midi: int = midi_of(pitch=pitch)
            place: tuple[int, int, int, Fraction, int] = (
                entry.voice_index,
                entry.note.staff - 1,
                entry.measure_index,
                entry.note.onset / _QUARTERS_PER_WHOLE,
                midi,
            )
            line: tuple[int, int, int] = (entry.voice_index, entry.note.staff - 1, midi)
            if entry.note.tie_stop:
                start: tuple[int, int, int, Fraction, int] | None = pending.pop(line, None)
                if start is None:
                    self._lost_tie(source=source, measure_index=entry.measure_index, issues=issues)
                else:
                    pairs.append(TiePair(start=start, end=place))

            if entry.note.tie_start:
                if line in pending:
                    self._lost_tie(source=source, measure_index=entry.measure_index, issues=issues)

                pending[line] = place

        for place in pending.values():
            self._lost_tie(source=source, measure_index=place[2], issues=issues)

        return pairs

    def _lost_tie(
        self, *, source: SourceScore, measure_index: int, issues: list[ImportIssue]
    ) -> None:
        issues.append(
            ImportIssue(
                kind=IssueKind.SKIPPED,
                measure=source.measures[measure_index].number,
                message="A tie with no note to join, or to a note that is not imported, "
                "is not imported.",
            )
        )

    def _graces(
        self,
        *,
        graces: list[tuple[int, SourceNote, int, DottedRhythmicValue, Accidental]],
        entries: list[Entry],
        source: SourceScore,
        issues: list[ImportIssue],
    ) -> dict[int, list[GraceEntry]]:
        leads: dict[tuple[int, int, Fraction], Entry] = {
            (entry.measure_index, entry.voice_index, entry.note.onset): entry
            for entry in entries
            if entry.rank == 0
        }
        # host -> grace notes in the order of the file, with the host's own place and placement
        hosts: dict[
            tuple[int, int, Fraction, GracePlacement],
            list[tuple[SourceNote, DottedRhythmicValue, Accidental]],
        ] = {}
        for measure_index, note, voice_index, value, accidental in graces:
            host: Entry | None = leads.get((measure_index, voice_index, note.onset))
            placement: GracePlacement = GracePlacement.BEFORE
            if host is None:
                host = next(
                    (
                        entry
                        for (m, v, _), entry in leads.items()
                        if m == measure_index
                        and v == voice_index
                        and self._end_of(entry=entry) == note.onset
                    ),
                    None,
                )
                placement = GracePlacement.AFTER

            if host is None:
                issues.append(
                    ImportIssue(
                        kind=IssueKind.SKIPPED,
                        measure=source.measures[measure_index].number,
                        message="A grace note with no note to belong to is not imported.",
                    )
                )
                continue

            hosts.setdefault(
                (host.measure_index, host.voice_index, host.note.onset, placement), []
            ).append((note, value, accidental))

        planned: dict[int, list[GraceEntry]] = {}
        for (measure_index, voice_index, onset, placement), notes in hosts.items():
            item_index: int = -1
            for step, (note, value, accidental) in enumerate(notes):
                is_lead: bool = not note.is_chord_member or item_index < 0
                if is_lead:
                    item_index += 1

                planned.setdefault(step, []).append(
                    GraceEntry(
                        host_voice=voice_index,
                        host_measure=measure_index,
                        host_position=onset / _QUARTERS_PER_WHOLE,
                        placement=placement,
                        note=note,
                        value=value,
                        accidental=accidental,
                        item_index=item_index,
                        is_lead=is_lead,
                    )
                )

        return planned

    def _end_of(self, *, entry: Entry) -> Fraction:
        written: Fraction = entry.value.fraction * _QUARTERS_PER_WHOLE
        return entry.note.onset + (
            entry.note.duration if entry.note.tuplet is not None else written
        )
