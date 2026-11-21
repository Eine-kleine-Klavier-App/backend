from dataclasses import dataclass, field
from fractions import Fraction
from xml.etree.ElementTree import Element, ParseError

from defusedxml import DefusedXmlException
from defusedxml import ElementTree as SafeElementTree

from piano_app.application.ports.importing import (
    ImportIssue,
    ImportRefusedError,
    IssueKind,
    SourceBarline,
    SourceClef,
    SourceDynamic,
    SourceKey,
    SourceMeasure,
    SourceNote,
    SourceOctaveShift,
    SourcePedal,
    SourcePitch,
    SourceScore,
    SourceSlur,
    SourceTempo,
    SourceTime,
    SourceWedge,
)

from .archive import ZIP_MAGIC, xml_bytes_of
from .marks import NoteMarks, read_marks

MAX_STAVES: int = 2
MAX_MEASURES: int = 10_000
MAX_NOTES: int = 200_000

_EXTENSIONS: tuple[str, ...] = (".musicxml", ".xml", ".mxl")

# What a note or a measure may carry that says nothing about the music: how it is drawn, how it is
# played back or how the file was made. Never reported.
_IGNORED_NOTE_CHILDREN: frozenset[str] = frozenset(
    {
        "pitch",
        "rest",
        "chord",
        "grace",
        "duration",
        "voice",
        "type",
        "dot",
        "tie",
        "staff",
        "time-modification",
        "beam",
        "stem",
        "accidental",
        "notehead",
        "notehead-text",
        "instrument",
        "play",
        "footnote",
        "level",
        "notations",
    }
)
_NOTE_CHILDREN_WITH_OWN_ISSUE: frozenset[str] = frozenset({"unpitched", "cue"})
_IGNORED_ATTRIBUTES_CHILDREN: frozenset[str] = frozenset(
    {"divisions", "key", "time", "clef", "staves", "footnote", "level"}
)
_HANDLED_MEASURE_CHILDREN: frozenset[str] = frozenset(
    {"attributes", "note", "backup", "forward", "direction", "barline"}
)


class MusicXmlReader:
    """Reads a MusicXML file (``.musicxml``, ``.xml`` or the compressed ``.mxl``) into the source
    score: one part of one or two staves, partwise.

    Everything the score has no place for goes into the issues of the result, with the number of
    the measure it stood in; the notes themselves are read as written, nothing is resolved here.
    """

    def detect(self, *, head: bytes, filename: str) -> bool:
        if not filename.lower().endswith(_EXTENSIONS):
            return False

        return head.startswith(ZIP_MAGIC) or b"<" in head

    def read(self, *, data: bytes) -> SourceScore:
        document: bytes = xml_bytes_of(data=data)

        try:
            root: Element = SafeElementTree.fromstring(document)
        except (ParseError, DefusedXmlException) as error:
            raise ImportRefusedError(reason="The file is not readable MusicXML.") from error

        if root.tag == "score-timewise":
            raise ImportRefusedError(reason="Timewise MusicXML is not supported yet.")

        if root.tag != "score-partwise":
            raise ImportRefusedError(reason="The file is not MusicXML.")

        parts: list[Element] = root.findall("part")
        if not parts:
            raise ImportRefusedError(reason="The file holds no music.")

        if len(parts) > 1:
            raise ImportRefusedError(
                reason="Files with several parts are not supported yet; "
                "only one part of one or two staves is imported."
            )

        title: str | None = None
        for credit in root.findall("credit"):
            if _text(credit.findtext("credit-type")) != "title":
                continue

            words: list[str] = []
            for credit_words in credit.findall("credit-words"):
                text: str | None = _text(credit_words.text)
                if text is not None:
                    words.append(text)

            if words:
                title = " ".join(words)
                break

        if title is None:
            title = _text(root.findtext("work/work-title")) or _text(
                root.findtext("movement-title")
            )

        return _PartReader(part=parts[0], title=title).read()


@dataclass(kw_only=True)
class _MeasureState:
    """What one measure collects as it is read."""

    number: str
    notes: list[SourceNote] = field(default_factory=list)
    clefs: list[SourceClef] = field(default_factory=list)
    keys: list[SourceKey] = field(default_factory=list)
    dynamics: list[SourceDynamic] = field(default_factory=list)
    wedges: list[SourceWedge] = field(default_factory=list)
    tempos: list[SourceTempo] = field(default_factory=list)
    pedals: list[SourcePedal] = field(default_factory=list)
    octave_shifts: list[SourceOctaveShift] = field(default_factory=list)
    slurs: list[SourceSlur] = field(default_factory=list)
    barlines: list[SourceBarline] = field(default_factory=list)


class _PartReader:
    def __init__(self, *, part: Element, title: str | None) -> None:
        self._part: Element = part
        self._title: str | None = title
        self._issues: list[ImportIssue] = []
        self._reported: set[tuple[IssueKind, str | None, Fraction | None, str]] = set()
        self._divisions: int | None = None
        self._time: SourceTime | None = None
        self._staves: int = 1
        self._note_count: int = 0

    def read(self) -> SourceScore:
        measures: list[SourceMeasure] = []

        for index, element in enumerate(self._part.findall("measure")):
            if index >= MAX_MEASURES:
                raise ImportRefusedError(reason="The file has too many measures.")

            measures.append(self._read_measure(element=element, index=index))

        if not measures:
            raise ImportRefusedError(reason="The file holds no measures.")

        return SourceScore(
            title=self._title,
            staff_count=self._staves,
            measures=tuple(measures),
            issues=tuple(self._issues),
        )

    def _issue(
        self, *, kind: IssueKind, measure: str | None, onset: Fraction | None, message: str
    ) -> None:
        key: tuple[IssueKind, str | None, Fraction | None, str] = (kind, measure, onset, message)
        if key in self._reported:
            return

        self._reported.add(key)
        self._issues.append(ImportIssue(kind=kind, measure=measure, onset=onset, message=message))

    def _read_measure(self, *, element: Element, index: int) -> SourceMeasure:
        number: str = element.get("number") or str(index + 1)
        state: _MeasureState = _MeasureState(number=number)
        cursor: Fraction = Fraction(0)
        extent: Fraction = Fraction(0)
        chord_onset: Fraction = Fraction(0)

        for child in element:
            if child.tag == "attributes":
                self._read_attributes(element=child, state=state, onset=cursor)
            elif child.tag == "note":
                note_onset: Fraction = cursor
                if child.find("chord") is not None:
                    note_onset = chord_onset

                note: SourceNote | None = self._read_note(
                    element=child, state=state, onset=note_onset
                )
                advance: Fraction = self._duration_of(element=child)
                if note is not None:
                    state.notes.append(note)

                if child.find("chord") is None:
                    chord_onset = cursor
                    cursor += advance
                    extent = max(extent, cursor)
            elif child.tag == "backup":
                cursor -= self._duration_of(element=child)
                cursor = max(cursor, Fraction(0))
            elif child.tag == "forward":
                cursor += self._duration_of(element=child)
                extent = max(extent, cursor)
            elif child.tag == "direction":
                self._read_direction(element=child, state=state, onset=cursor)
            elif child.tag == "barline":
                self._read_barline(element=child, state=state)
            elif child.tag not in _HANDLED_MEASURE_CHILDREN:
                self._issue(
                    kind=IssueKind.SKIPPED,
                    measure=number,
                    # a line or page break is the layout of the file, not a place in the music
                    onset=None if child.tag == "print" else cursor,
                    message=f"<{child.tag}> is not imported.",
                )

        if self._time is None:
            raise ImportRefusedError(reason="The file has no time signature.")

        self._note_count += len(state.notes)
        if self._note_count > MAX_NOTES:
            raise ImportRefusedError(reason="The file has too many notes.")

        return SourceMeasure(
            number=number,
            index=index,
            time=self._time,
            is_implicit=element.get("implicit") == "yes",
            extent=extent,
            notes=tuple(state.notes),
            clefs=tuple(state.clefs),
            keys=tuple(state.keys),
            dynamics=tuple(state.dynamics),
            wedges=tuple(state.wedges),
            tempos=tuple(state.tempos),
            pedals=tuple(state.pedals),
            octave_shifts=tuple(state.octave_shifts),
            slurs=tuple(state.slurs),
            barlines=tuple(state.barlines),
        )

    def _read_direction(self, *, element: Element, state: _MeasureState, onset: Fraction) -> None:
        staff: int = _int(text=element.findtext("staff") or "1", what="direction staff")
        for kind in element.findall("direction-type"):
            for child in kind:
                self._read_direction_child(child=child, state=state, onset=onset, staff=staff)

        sound: Element | None = element.find("sound")
        tempo: str | None = sound.get("tempo") if sound is not None else None
        if tempo is not None and not state.tempos:
            self._add_tempo(state=state, onset=onset, text=tempo, beat_type=None, dots=0)

    def _read_direction_child(
        self, *, child: Element, state: _MeasureState, onset: Fraction, staff: int
    ) -> None:
        if child.tag == "dynamics":
            for mark in child:
                state.dynamics.append(SourceDynamic(onset=onset, marking=mark.tag, staff=staff))
        elif child.tag == "wedge":
            wedge_kind: str | None = child.get("type")
            if wedge_kind in ("crescendo", "diminuendo", "stop"):
                state.wedges.append(SourceWedge(onset=onset, kind=wedge_kind, staff=staff))
        elif child.tag == "pedal":
            pedal_kind: str | None = child.get("type")
            if pedal_kind in ("start", "stop", "change", "continue"):
                state.pedals.append(SourcePedal(onset=onset, kind=pedal_kind))
        elif child.tag == "octave-shift":
            shift_kind: str | None = child.get("type")
            if shift_kind in ("up", "down", "stop"):
                state.octave_shifts.append(
                    SourceOctaveShift(
                        onset=onset,
                        staff=staff,
                        kind=shift_kind,
                        size=_int(text=child.get("size") or "8", what="octave shift"),
                    )
                )
        elif child.tag == "metronome":
            per_minute: str | None = child.findtext("per-minute")
            if per_minute is not None:
                self._add_tempo(
                    state=state,
                    onset=onset,
                    text=per_minute,
                    beat_type=_text(child.findtext("beat-unit")),
                    dots=len(child.findall("beat-unit-dot")),
                )
        else:
            self._issue(
                kind=IssueKind.SKIPPED,
                measure=state.number,
                onset=onset,
                message=f"<{child.tag}> is not imported.",
            )

    def _add_tempo(
        self,
        *,
        state: _MeasureState,
        onset: Fraction,
        text: str,
        beat_type: str | None,
        dots: int,
    ) -> None:
        try:
            bpm: int = round(float(text))
        except ValueError:
            self._issue(
                kind=IssueKind.SKIPPED,
                measure=state.number,
                onset=onset,
                message="A tempo that is not a number is not imported.",
            )
            return

        if bpm < 1:
            return

        state.tempos.append(SourceTempo(onset=onset, bpm=bpm, beat_type=beat_type, dots=dots))

    def _read_barline(self, *, element: Element, state: _MeasureState) -> None:
        repeat: Element | None = element.find("repeat")
        ending: Element | None = element.find("ending")
        if repeat is None and ending is None:
            return

        times: str | None = repeat.get("times") if repeat is not None else None
        state.barlines.append(
            SourceBarline(
                location=element.get("location") or "right",
                repeat=repeat.get("direction") if repeat is not None else None,
                times=int(times) if times is not None and times.isdigit() else None,
                ending_number=ending.get("number") if ending is not None else None,
                ending_kind=ending.get("type") if ending is not None else None,
            )
        )

    def _read_attributes(
        self,
        *,
        element: Element,
        state: _MeasureState,
        onset: Fraction,
    ) -> None:
        for child in element:
            if child.tag == "divisions":
                self._divisions = _positive_int(text=child.text, what="divisions")
            elif child.tag == "staves":
                self._staves = _positive_int(text=child.text, what="staves")
                if self._staves > MAX_STAVES:
                    raise ImportRefusedError(
                        reason="Parts with more than two staves are not supported."
                    )
            elif child.tag == "time":
                self._time = self._read_time(element=child)
            elif child.tag == "key":
                fifths: str | None = child.findtext("fifths")
                if fifths is None:
                    self._issue(
                        kind=IssueKind.SKIPPED,
                        measure=state.number,
                        onset=onset,
                        message="A key without a number of fifths is not imported.",
                    )
                else:
                    state.keys.append(SourceKey(onset=onset, fifths=_int(text=fifths, what="key")))
            elif child.tag == "clef":
                clef: SourceClef | None = self._read_clef(element=child, onset=onset)
                if clef is not None:
                    state.clefs.append(clef)
            elif child.tag not in _IGNORED_ATTRIBUTES_CHILDREN:
                self._issue(
                    kind=IssueKind.SKIPPED,
                    measure=state.number,
                    onset=onset,
                    message=f"<{child.tag}> is not imported.",
                )

    def _read_time(self, *, element: Element) -> SourceTime:
        beats: str | None = element.findtext("beats")
        beat_type: str | None = element.findtext("beat-type")
        if beats is None or beat_type is None:
            raise ImportRefusedError(reason="A time signature of this kind is not supported.")

        if not beats.strip().isdigit() or not beat_type.strip().isdigit():
            raise ImportRefusedError(reason="A composite time signature is not supported yet.")

        return SourceTime(beats=int(beats), beat_type=int(beat_type))

    def _read_clef(self, *, element: Element, onset: Fraction) -> SourceClef | None:
        sign: str | None = _text(element.findtext("sign"))
        if sign is None:
            return None

        line: str | None = element.findtext("line")
        octave_change: str | None = element.findtext("clef-octave-change")

        return SourceClef(
            staff=_int(text=element.get("number") or "1", what="clef staff"),
            onset=onset,
            sign=sign,
            line=_int(text=line, what="clef line") if line is not None else None,
            octave_change=(
                _int(text=octave_change, what="clef octave") if octave_change is not None else 0
            ),
        )

    def _duration_of(self, *, element: Element) -> Fraction:
        text: str | None = element.findtext("duration")
        if text is None:
            return Fraction(0)

        if self._divisions is None:
            raise ImportRefusedError(reason="The file gives no divisions per quarter note.")

        return Fraction(_int(text=text, what="duration"), self._divisions)

    def _read_note(
        self, *, element: Element, state: _MeasureState, onset: Fraction
    ) -> SourceNote | None:
        number: str = state.number
        for child in element:
            if child.tag in _NOTE_CHILDREN_WITH_OWN_ISSUE:
                self._issue(
                    kind=IssueKind.SKIPPED,
                    measure=number,
                    onset=onset,
                    message=f"A {child.tag} note is not imported.",
                )
                return None

            if child.tag not in _IGNORED_NOTE_CHILDREN:
                self._issue(
                    kind=IssueKind.SKIPPED,
                    measure=number,
                    onset=onset,
                    message=f"<{child.tag}> is not imported.",
                )

        pitch: SourcePitch | None = None
        pitch_element: Element | None = element.find("pitch")
        if pitch_element is not None:
            pitch = self._read_pitch(element=pitch_element, number=number, onset=onset)

        rest: Element | None = element.find("rest")
        grace: Element | None = element.find("grace")
        is_grace: bool = grace is not None
        tuplet: tuple[int, int] | None = None
        modification: Element | None = element.find("time-modification")
        if modification is not None:
            tuplet = (
                _positive_int(text=modification.findtext("actual-notes"), what="tuplet"),
                _positive_int(text=modification.findtext("normal-notes"), what="tuplet"),
            )

        tie_types: list[str | None] = [tie.get("type") for tie in element.findall("tie")]
        voice: int = _int(text=element.findtext("voice") or "1", what="voice")
        staff: int = _int(text=element.findtext("staff") or "1", what="staff")
        marks: NoteMarks = read_marks(notations=element.findall("notations"))
        for slur_kind, slur_number in marks.slurs:
            state.slurs.append(
                SourceSlur(
                    onset=onset, kind=slur_kind, number=slur_number, voice=voice, staff=staff
                )
            )

        for name in marks.skipped:
            self._issue(
                kind=IssueKind.SKIPPED,
                measure=number,
                onset=onset,
                message=f"<{name}> is not imported.",
            )

        return SourceNote(
            onset=onset,
            duration=Fraction(0) if is_grace else self._duration_of(element=element),
            voice=voice,
            staff=staff,
            pitch=pitch,
            written_type=_text(element.findtext("type")),
            dots=len(element.findall("dot")),
            tuplet=tuplet,
            is_chord_member=element.find("chord") is not None,
            is_grace=is_grace,
            is_slashed=grace is not None and grace.get("slash") == "yes",
            is_measure_rest=rest is not None and rest.get("measure") == "yes",
            tie_start="start" in tie_types,
            tie_stop="stop" in tie_types,
            articulations=frozenset(marks.articulations),
            ornament=marks.ornament,
            fingering=marks.fingering,
            beam=_first_beam_of(element=element),
            stem=_stem_of(element=element),
        )

    def _read_pitch(self, *, element: Element, number: str, onset: Fraction) -> SourcePitch:
        step: str | None = _text(element.findtext("step"))
        octave: str | None = element.findtext("octave")
        if step is None or step not in "CDEFGAB" or len(step) != 1 or octave is None:
            raise ImportRefusedError(reason="A note has a pitch that cannot be read.")

        alter_text: str | None = element.findtext("alter")
        alter: int = 0
        if alter_text is not None:
            try:
                exact: float = float(alter_text)
            except ValueError as error:
                raise ImportRefusedError(
                    reason="A note has an accidental that cannot be read."
                ) from error

            alter = round(exact)
            if alter != exact:
                self._issue(
                    kind=IssueKind.CHANGED,
                    measure=number,
                    onset=onset,
                    message="A microtone was rounded to the nearest semitone.",
                )

        return SourcePitch(step=step, alter=alter, octave=_int(text=octave, what="octave"))


def _first_beam_of(*, element: Element) -> str | None:
    """The state of the note in the first beam of the file (a hook is a note value, not a beam)."""
    for beam in element.findall("beam"):
        if beam.get("number", "1") == "1" and beam.text is not None:
            state: str = beam.text.strip()
            return state if state in ("begin", "continue", "end") else None

    return None


def _stem_of(*, element: Element) -> str | None:
    """``"up"`` or ``"down"`` when the file draws the stem so; ``none`` and ``double`` say none."""
    stem: str | None = _text(element.findtext("stem"))
    return stem if stem in ("up", "down") else None


def _text(value: str | None) -> str | None:
    if value is None:
        return None

    stripped: str = value.strip()

    return stripped or None


def _int(*, text: str | None, what: str) -> int:
    if text is None:
        raise ImportRefusedError(reason=f"The file has no value for {what}.")

    try:
        return int(text.strip())
    except ValueError as error:
        raise ImportRefusedError(reason=f"The file has a {what} that is not a number.") from error


def _positive_int(*, text: str | None, what: str) -> int:
    value: int = _int(text=text, what=what)
    if value < 1:
        raise ImportRefusedError(reason=f"The file has a {what} that is not positive.")

    return value
