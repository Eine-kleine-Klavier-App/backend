from fractions import Fraction

from tests.unit.application.test_score_builder import _attributes, _build, _measure, _note, _rest

from piano_app.adapters.outbound.importers.musicxml.reader import MusicXmlReader
from piano_app.application.ports.importing import SourceScore
from piano_app.application.use_cases.score.import_score.compare import (
    ComparisonIssue,
    ScoreComparer,
)
from piano_app.domain.score.document.models import ScoreDocument


def _source(*measures: str) -> SourceScore:
    xml: bytes = (
        "<score-partwise><part-list/><part id='P1'>"
        + "".join(measures)
        + "</part></score-partwise>"
    ).encode()
    return MusicXmlReader().read(data=xml)


def _compare(document: ScoreDocument, source: SourceScore) -> list[tuple[str, int | None, str]]:
    issues: tuple[ComparisonIssue, ...] = ScoreComparer().compare(document=document, source=source)
    return [(issue.kind.value, issue.measure_index, issue.message) for issue in issues]


def _three(*, first: str = "C", beats: int = 3) -> str:
    return _measure(
        1,
        attributes=_attributes(beats=beats),
        body=_note(first, 5) + _note("D", 5) + _note("E", 5),
    )


def test_a_draft_built_from_the_file_has_no_difference() -> None:
    measures = (_three(), _measure(2, body=_note("F", 5) + _note("G", 5) + _rest()))

    assert _compare(_build(*measures).document, _source(*measures)) == []


def test_notes_of_the_file_that_the_draft_lacks_and_notes_it_has_extra_are_named() -> None:
    document = _build(_three(first="C")).document

    assert _compare(document, _source(_three(first="B"))) == [
        ("mismatch", 0, "In the file but not in the draft: B5 at beat 1."),
        ("mismatch", 0, "In the draft but not in the file: C5 at beat 1."),
    ]


def test_a_note_of_another_length_is_named() -> None:
    whole = _measure(
        1, attributes=_attributes(beats=4), body=_note("C", 5, duration=8, kind="whole")
    )
    half = _measure(
        1,
        attributes=_attributes(beats=4),
        body=_note("C", 5, duration=4, kind="half") + _rest(duration=4, kind="half"),
    )

    assert _compare(_build(whole).document, _source(half)) == [
        ("mismatch", 0, "A different length in the draft: C5 at beat 1.")
    ]


def test_a_different_number_or_length_of_measures_is_named() -> None:
    document = _build(_three(), _measure(2, body=_note("F", 5) + _note("G", 5) + _rest())).document

    assert _compare(document, _source(_three())) == [
        ("mismatch", None, "The file has 1 measures, the draft has 2."),
        ("mismatch", 1, "In the draft but not in the file: F5 at beat 1."),
        ("mismatch", 1, "In the draft but not in the file: G5 at beat 2."),
    ]
    assert _compare(_build(_three(beats=3)).document, _source(_three(beats=4))) == [
        ("mismatch", 0, "The file's measure is 4/4, the draft's is 3/4.")
    ]


def test_each_difference_stands_at_its_own_beat_and_a_measure_wide_one_at_none() -> None:
    words = "<direction><direction-type><words>dolce</words></direction-type></direction>"
    second = _measure(2, body=_note("F", 5) + words + _note("G", 5) + _rest())
    document = _build(_three(), _measure(2, body=_note("F", 5) + _note("A", 5) + _rest())).document

    issues = ScoreComparer().compare(document=document, source=_source(_three(), second))
    wider = ScoreComparer().compare(
        document=_build(_three(beats=3)).document, source=_source(_three(beats=4))
    )

    assert [(issue.measure_index, issue.onset, issue.message) for issue in issues] == [
        (1, Fraction(1), "<words> is not imported."),
        (1, Fraction(1), "In the file but not in the draft: G5 at beat 2."),
        (1, Fraction(1), "In the draft but not in the file: A5 at beat 2."),
    ]
    assert [issue.onset for issue in wider] == [None]


def test_what_the_reader_left_out_is_tied_to_the_measure_of_the_draft_by_its_label() -> None:
    pickup = _measure(0, attributes=_attributes(beats=4), body=_note("C", 5), implicit=True)
    words = "<direction><direction-type><words>dolce</words></direction-type></direction>"
    second = _measure(1, body=words + _note("D", 5, duration=8, kind="whole"))
    measures = (pickup, second)

    assert _compare(_build(*measures).document, _source(*measures)) == [
        ("skipped", 1, "<words> is not imported.")
    ]
