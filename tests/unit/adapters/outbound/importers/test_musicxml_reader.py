from fractions import Fraction
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from piano_app.adapters.outbound.importers.musicxml import archive
from piano_app.adapters.outbound.importers.musicxml.reader import MusicXmlReader
from piano_app.application.ports.importing import (
    ImportIssue,
    ImportRefusedError,
    IssueKind,
    SourceNote,
    SourceScore,
)

_ATTRIBUTES: str = """
  <attributes>
    <divisions>2</divisions>
    <key><fifths>1</fifths></key>
    <time><beats>3</beats><beat-type>4</beat-type></time>
    <staves>2</staves>
    <clef number="1"><sign>G</sign><line>2</line></clef>
    <clef number="2"><sign>F</sign><line>4</line></clef>
  </attributes>"""


def _score(*, measures: str, part_count: int = 1, header: str = "") -> bytes:
    parts: str = "".join(
        f'<part id="P{number}">{measures}</part>' for number in range(1, part_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" '
        '"http://www.musicxml.org/dtds/partwise.dtd">'
        f"<score-partwise><work><work-title>Etude</work-title></work>{header}{parts}</score-partwise>"
    ).encode()


def _read(*, measures: str, **keywords: object) -> SourceScore:
    return MusicXmlReader().read(data=_score(measures=measures, **keywords))  # type: ignore[arg-type]


def _issues(score: SourceScore, kind: IssueKind) -> list[ImportIssue]:
    return [issue for issue in score.issues if issue.kind is kind]


_FIRST_MEASURE: str = f"""
<measure number="1">{_ATTRIBUTES}
  <note><pitch><step>C</step><octave>5</octave></pitch><duration>2</duration><voice>1</voice>
    <type>quarter</type><staff>1</staff></note>
  <note><pitch><step>E</step><alter>-1</alter><octave>5</octave></pitch><duration>2</duration>
    <voice>1</voice><type>quarter</type><staff>1</staff><tie type="start"/></note>
  <note><chord/><pitch><step>G</step><octave>5</octave></pitch><duration>2</duration>
    <voice>1</voice><type>quarter</type><staff>1</staff></note>
  <note><rest/><duration>2</duration><voice>1</voice><type>quarter</type><staff>1</staff></note>
  <backup><duration>6</duration></backup>
  <note><pitch><step>C</step><octave>3</octave></pitch><duration>6</duration><voice>2</voice>
    <type>half</type><dot/><staff>2</staff></note>
</measure>"""


def test_a_measure_is_read_as_written_with_onsets_in_quarter_notes() -> None:
    score: SourceScore = _read(measures=_FIRST_MEASURE)

    (measure,) = score.measures
    assert score.title == "Etude"
    assert score.staff_count == 2
    assert (measure.time.beats, measure.time.beat_type) == (3, 4)
    assert measure.keys[0].fifths == 1
    assert [(clef.staff, clef.sign, clef.line) for clef in measure.clefs] == [
        (1, "G", 2),
        (2, "F", 4),
    ]
    assert measure.extent == Fraction(3)

    upper: list[SourceNote] = [note for note in measure.notes if note.voice == 1]
    assert [(note.onset, note.duration) for note in upper] == [
        (Fraction(0), Fraction(1)),
        (Fraction(1), Fraction(1)),
        (Fraction(1), Fraction(1)),
        (Fraction(2), Fraction(1)),
    ]
    flat: SourceNote = upper[1]
    assert flat.pitch is not None and (flat.pitch.step, flat.pitch.alter) == ("E", -1)
    assert flat.tie_start and not flat.tie_stop
    assert upper[2].is_chord_member
    assert upper[3].pitch is None

    lower: SourceNote = next(note for note in measure.notes if note.voice == 2)
    assert (lower.onset, lower.duration, lower.staff, lower.dots) == (
        Fraction(0),
        Fraction(3),
        2,
        1,
    )
    assert lower.written_type == "half"


def test_a_file_with_a_doctype_is_read() -> None:
    score: SourceScore = _read(measures=_FIRST_MEASURE)

    assert len(score.measures) == 1


def test_the_time_signature_in_force_follows_into_later_measures() -> None:
    second: str = """<measure number="2" implicit="yes">
      <note><rest measure="yes"/><duration>2</duration></note></measure>"""

    score: SourceScore = _read(measures=_FIRST_MEASURE + second)

    assert [(m.number, m.time.beats, m.is_implicit) for m in score.measures] == [
        ("1", 3, False),
        ("2", 3, True),
    ]
    assert score.measures[1].notes[0].is_measure_rest


def test_a_tuplet_and_a_grace_note_are_read() -> None:
    measures: str = f"""<measure number="1">{_ATTRIBUTES}
      <note><grace/><pitch><step>D</step><octave>5</octave></pitch><type>eighth</type></note>
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration>
        <type>eighth</type><time-modification><actual-notes>3</actual-notes>
        <normal-notes>2</normal-notes></time-modification></note></measure>"""

    grace, triplet = _read(measures=measures).measures[0].notes

    assert grace.is_grace and grace.duration == 0 and grace.onset == 0
    assert triplet.tuplet == (3, 2)


def test_what_the_score_has_no_place_for_is_reported_with_its_measure() -> None:
    measures: str = f"""<measure number="7">{_ATTRIBUTES}
      <direction><direction-type><words>dolce</words></direction-type></direction>
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>2</duration>
        <type>quarter</type><lyric><text>la</text></lyric></note></measure>"""

    skipped: list[ImportIssue] = _issues(_read(measures=measures), IssueKind.SKIPPED)

    assert [(issue.measure, issue.message) for issue in skipped] == [
        ("7", "<words> is not imported."),
        ("7", "<lyric> is not imported."),
    ]


def test_what_is_left_out_is_reported_at_its_beat_and_a_break_at_none() -> None:
    measures: str = f"""<measure number="1">{_ATTRIBUTES}
      <print new-system="yes"/>
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>2</duration>
        <type>quarter</type></note>
      <direction><direction-type><words>cresc.</words></direction-type></direction>
      <note><pitch><step>D</step><octave>5</octave></pitch><duration>2</duration>
        <type>quarter</type><lyric><text>la</text></lyric></note></measure>"""

    skipped: list[ImportIssue] = _issues(_read(measures=measures), IssueKind.SKIPPED)

    assert [(issue.message, issue.onset) for issue in skipped] == [
        ("<print> is not imported.", None),
        ("<words> is not imported.", Fraction(1)),
        ("<lyric> is not imported.", Fraction(1)),
    ]


def test_the_first_beam_and_the_stem_of_a_note_are_read() -> None:
    measures: str = f"""<measure number="1">{_ATTRIBUTES}
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration><voice>1</voice>
        <type>eighth</type><stem>down</stem><staff>1</staff>
        <beam number="1">begin</beam><beam number="2">begin</beam></note>
      <note><pitch><step>D</step><octave>5</octave></pitch><duration>1</duration><voice>1</voice>
        <type>16th</type><stem>down</stem><staff>1</staff>
        <beam number="1">continue</beam><beam number="2">forward hook</beam></note>
      <note><pitch><step>E</step><octave>5</octave></pitch><duration>1</duration><voice>1</voice>
        <type>eighth</type><stem>none</stem><staff>1</staff><beam number="1">end</beam></note>
      <note><pitch><step>G</step><octave>5</octave></pitch><duration>3</duration><voice>1</voice>
        <type>half</type><staff>1</staff></note></measure>"""

    notes = _read(measures=measures).measures[0].notes

    assert [(note.beam, note.stem) for note in notes] == [
        ("begin", "down"),
        ("continue", "down"),
        ("end", None),
        (None, None),
    ]


def test_a_dynamic_and_a_wedge_say_the_staff_they_are_put_on() -> None:
    measures: str = f"""<measure number="1">{_ATTRIBUTES}
      <direction><direction-type><dynamics><mf/></dynamics></direction-type></direction>
      <direction><direction-type><dynamics><p/></dynamics></direction-type><staff>2</staff></direction>
      <direction><direction-type><wedge type="crescendo"/></direction-type><staff>2</staff>
      </direction></measure>"""

    measure = _read(measures=measures).measures[0]

    assert [(dynamic.marking, dynamic.staff) for dynamic in measure.dynamics] == [
        ("mf", 1),
        ("p", 2),
    ]
    assert [(wedge.kind, wedge.staff) for wedge in measure.wedges] == [("crescendo", 2)]


def test_a_microtone_is_rounded_and_reported() -> None:
    measures: str = f"""<measure number="1">{_ATTRIBUTES}
      <note><pitch><step>C</step><alter>0.5</alter><octave>5</octave></pitch>
        <duration>2</duration><type>quarter</type></note></measure>"""

    score: SourceScore = _read(measures=measures)

    note: SourceNote = score.measures[0].notes[0]
    assert note.pitch is not None and note.pitch.alter == 0
    assert [issue.kind for issue in score.issues] == [IssueKind.CHANGED]


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"not xml at all", "not readable"),
        (b"<score-timewise/>", "Timewise"),
        (b"<html/>", "not MusicXML"),
        (b"<score-partwise></score-partwise>", "no music"),
        (_score(measures=_FIRST_MEASURE, part_count=2), "several parts"),
        (
            _score(measures=_FIRST_MEASURE.replace("<staves>2</staves>", "<staves>3</staves>")),
            "more than two staves",
        ),
        (
            _score(
                measures="<measure number='1'><attributes><divisions>1</divisions>"
                "</attributes></measure>"
            ),
            "no time signature",
        ),
        (
            _score(measures=_FIRST_MEASURE.replace("<beats>3</beats>", "<beats>3+2</beats>")),
            "composite",
        ),
    ],
)
def test_a_file_that_cannot_be_imported_is_refused_with_a_reason(data: bytes, reason: str) -> None:
    with pytest.raises(ImportRefusedError, match=reason):
        MusicXmlReader().read(data=data)


def test_an_entity_bomb_is_refused() -> None:
    bomb: bytes = (
        b'<?xml version="1.0"?><!DOCTYPE score-partwise [<!ENTITY a "aaaaaaaaaa">'
        b'<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]><score-partwise>&b;</score-partwise>'
    )

    with pytest.raises(ImportRefusedError, match="not readable"):
        MusicXmlReader().read(data=bomb)


def _mxl(*, document: bytes, container: bytes | None = None) -> bytes:
    default: bytes = (
        b'<container><rootfiles><rootfile full-path="score.xml"/></rootfiles></container>'
    )
    buffer: BytesIO = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive_file:
        archive_file.writestr("META-INF/container.xml", container or default)
        archive_file.writestr("score.xml", document)

    return buffer.getvalue()


def test_a_compressed_file_is_read_through_its_container() -> None:
    data: bytes = _mxl(document=_score(measures=_FIRST_MEASURE))

    score: SourceScore = MusicXmlReader().read(data=data)

    assert len(score.measures) == 1


def test_a_compressed_file_that_is_too_large_or_too_dense_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data: bytes = _mxl(document=_score(measures=_FIRST_MEASURE))

    monkeypatch.setattr(archive, "MAX_XML_BYTES", 100)
    with pytest.raises(ImportRefusedError, match="too large"):
        MusicXmlReader().read(data=data)

    monkeypatch.undo()
    monkeypatch.setattr(archive, "MAX_COMPRESSION_RATIO", 1)
    with pytest.raises(ImportRefusedError, match="plausible"):
        MusicXmlReader().read(data=data)

    monkeypatch.undo()
    with pytest.raises(ImportRefusedError, match=r"container\.xml"):
        MusicXmlReader().read(data=_mxl(document=b"<a/>", container=b"<container>"))


def test_a_file_is_recognised_by_its_name_and_its_first_bytes() -> None:
    reader: MusicXmlReader = MusicXmlReader()

    assert reader.detect(head=b'<?xml version="1.0"?>', filename="Etude.MUSICXML")
    assert reader.detect(head=b"PK\x03\x04", filename="etude.mxl")
    assert not reader.detect(head=b"%PDF-1.7", filename="etude.pdf")
    assert not reader.detect(head=b"binary", filename="etude.xml")


def _direction(*, body: str, staff: int = 1) -> str:
    return f"<direction><direction-type>{body}</direction-type><staff>{staff}</staff></direction>"


def test_marks_between_notes_are_read_with_their_onsets() -> None:
    measures: str = f"""<measure number="1">{_ATTRIBUTES}
      {_direction(body="<dynamics><mf/></dynamics>")}
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>2</duration>
        <type>quarter</type></note>
      {_direction(body='<wedge type="crescendo"/>')}
      <note><pitch><step>D</step><octave>5</octave></pitch><duration>2</duration>
        <type>quarter</type></note>
      {_direction(body='<wedge type="stop"/><dynamics><f/></dynamics>')}
      <direction><direction-type><metronome><beat-unit>quarter</beat-unit>
        <per-minute>96</per-minute></metronome></direction-type></direction>
      {_direction(body='<pedal type="start"/>')}
      {_direction(body='<octave-shift type="up" size="8"/>', staff=1)}
    </measure>"""

    (measure,) = _read(measures=measures).measures

    assert [(d.onset, d.marking) for d in measure.dynamics] == [
        (Fraction(0), "mf"),
        (Fraction(2), "f"),
    ]
    assert [(w.onset, w.kind) for w in measure.wedges] == [
        (Fraction(1), "crescendo"),
        (Fraction(2), "stop"),
    ]
    assert [(t.onset, t.bpm, t.beat_type) for t in measure.tempos] == [(Fraction(2), 96, "quarter")]
    assert [(p.onset, p.kind) for p in measure.pedals] == [(Fraction(2), "start")]
    assert [(s.kind, s.size, s.staff) for s in measure.octave_shifts] == [("up", 8, 1)]


def test_the_marks_of_a_note_are_read() -> None:
    notations: str = (
        "<notations><slur type='start' number='1'/><articulations><staccato/><accent/>"
        "</articulations><ornaments><trill-mark/></ornaments>"
        "<technical><fingering>3</fingering></technical><fermata/></notations>"
    )
    measures: str = f"""<measure number="1">{_ATTRIBUTES}
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>2</duration>
        <type>quarter</type>{notations}</note>
      <note><pitch><step>D</step><octave>5</octave></pitch><duration>2</duration>
        <type>quarter</type><notations><slur type="stop" number="1"/></notations></note>
    </measure>"""

    (measure,) = _read(measures=measures).measures

    first: SourceNote = measure.notes[0]
    assert first.articulations == {"staccato", "accent", "fermata"}
    assert (first.ornament, first.fingering) == ("trill-mark", 3)
    assert [(s.kind, s.onset, s.voice) for s in measure.slurs] == [
        ("start", Fraction(0), 1),
        ("stop", Fraction(1), 1),
    ]


def test_repeat_signs_and_endings_are_read_from_the_barlines() -> None:
    measures: str = f"""<measure number="1">{_ATTRIBUTES}
      <barline location="left"><repeat direction="forward"/></barline>
      <barline location="right"><ending number="1" type="stop"/>
        <repeat direction="backward" times="3"/></barline></measure>"""

    (measure,) = _read(measures=measures).measures

    assert [
        (b.location, b.repeat, b.times, b.ending_number, b.ending_kind) for b in measure.barlines
    ] == [
        ("left", "forward", None, None, None),
        ("right", "backward", 3, "1", "stop"),
    ]


def test_the_title_credit_wins_over_the_work_title() -> None:
    header: str = (
        "<credit><credit-type>composer</credit-type><credit-words>Coker</credit-words></credit>"
        "<credit><credit-type>title</credit-type><credit-words>Etude in C</credit-words></credit>"
    )

    score: SourceScore = _read(measures=_FIRST_MEASURE, header=header)

    assert score.title == "Etude in C"


def test_a_score_without_a_title_credit_is_named_by_its_work_title() -> None:
    header: str = (
        "<credit><credit-type>composer</credit-type><credit-words>Coker</credit-words></credit>"
    )

    score: SourceScore = _read(measures=_FIRST_MEASURE, header=header)

    assert score.title == "Etude"


def test_a_mark_the_score_has_no_place_for_is_reported() -> None:
    measures: str = f"""<measure number="3">{_ATTRIBUTES}
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>2</duration>
        <type>quarter</type><notations><ornaments><schleifer/></ornaments>
        <glissando type="start"/></notations></note></measure>"""

    skipped: list[ImportIssue] = _issues(_read(measures=measures), IssueKind.SKIPPED)

    assert [issue.message for issue in skipped] == [
        "<schleifer> is not imported.",
        "<glissando> is not imported.",
    ]
