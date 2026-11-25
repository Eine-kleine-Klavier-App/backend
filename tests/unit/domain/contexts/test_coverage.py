from fractions import Fraction

import pytest
from tests.unit.domain.document_builders import anchor, note, score

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import (
    Context,
    DynamicChange,
    Hairpin,
    OctaveTransposition,
    Slur,
    SustainHold,
    TempoChange,
)
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import (
    DottedRhythmicValue,
    DynamicMarking,
    RhythmicValue,
)
from piano_app.domain.score.document.services.contexts import ContextIndex, Coverage, covered_by
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry

# What a context is applied to: the elements that start inside its region [start, end), in what
# it governs. One rule for every kind; the note on the end anchor is not covered.

_BEATS: list[Fraction] = [Fraction(1) + Fraction(beat, 4) for beat in range(4)]


def _coverage(*, document: ScoreDocument, context: Context) -> Coverage:
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    return covered_by(
        context=context,
        document=document,
        geometry=geometry,
        contexts=ContextIndex(document=document, geometry=geometry),
    )


def _carriers(*, coverage: Coverage) -> list[str]:
    return [carrier.id for carrier in coverage.carriers]


def _two_voices() -> tuple[ScoreDocument, list[Note], list[Note]]:
    """Four beats of measure 1 in each of the two voices; the first voice on the first staff,
    the second on the second."""
    document: ScoreDocument = score()
    upper: list[Note] = [note(document, at, voice=0, staff=0) for at in _BEATS]
    lower: list[Note] = [note(document, at, voice=1, staff=1) for at in _BEATS]

    return document, upper, lower


@pytest.mark.unit
def test_a_slur_covers_the_notes_of_its_voices_up_to_but_not_the_note_it_lands_on() -> None:
    document, upper, _lower = _two_voices()
    slur: Slur = Slur.create(
        start=anchor(document, _BEATS[0]),
        end=anchor(document, _BEATS[3]),
        voice=document.voices[0],
    )

    coverage: Coverage = _coverage(document=document, context=slur)

    assert _carriers(coverage=coverage) == [item.note_carrier.id for item in upper[:3]]
    assert [item.id for item in coverage.notes] == [item.id for item in upper[:3]]


@pytest.mark.unit
def test_a_pedal_covers_every_voice() -> None:
    document, upper, lower = _two_voices()
    pedal: SustainHold = SustainHold.create(
        start=anchor(document, _BEATS[1]), end=anchor(document, _BEATS[3])
    )

    coverage: Coverage = _coverage(document=document, context=pedal)

    expected: set[str] = {item.note_carrier.id for item in (*upper[1:3], *lower[1:3])}
    assert set(_carriers(coverage=coverage)) == expected
    assert len(coverage.notes) == 4


@pytest.mark.unit
def test_an_octave_line_covers_only_the_notes_on_its_staff() -> None:
    document, upper, lower = _two_voices()
    # a chord across both staffs: the carrier is covered, only its note on the first staff is
    crossing: Note = Note.create(
        note_carrier=lower[1].note_carrier,
        staff=document.staffs[0],
        staff_step=4,
        accidental=lower[1].accidental,
    )
    line: OctaveTransposition = OctaveTransposition.create(
        start=anchor(document, _BEATS[0]),
        end=anchor(document, _BEATS[3]),
        staff=document.staffs[0],
        octaves=1,
    )

    coverage: Coverage = _coverage(document=document, context=line)

    assert [item.id for item in coverage.notes] == [
        upper[0].id,
        upper[1].id,
        crossing.id,
        upper[2].id,
    ]
    assert lower[0].note_carrier.id not in _carriers(coverage=coverage)
    assert lower[1].note_carrier.id in _carriers(coverage=coverage)


@pytest.mark.unit
def test_a_hairpin_covers_the_notes_of_its_voices() -> None:
    document, _upper, lower = _two_voices()
    hairpin: Hairpin = Hairpin.create(
        start=anchor(document, _BEATS[0]),
        end=anchor(document, _BEATS[2]),
        voice=document.voices[1],
        steps=1,
    )

    coverage: Coverage = _coverage(document=document, context=hairpin)

    assert [item.id for item in coverage.notes] == [item.id for item in lower[:2]]


@pytest.mark.unit
def test_a_tempo_covers_everything_until_the_next_tempo() -> None:
    document, upper, lower = _two_voices()
    quarter: DottedRhythmicValue = DottedRhythmicValue(value=RhythmicValue.QUARTER)
    first: TempoChange = TempoChange.create(
        start=anchor(document, _BEATS[1]), beat=quarter, bpm=100
    )
    TempoChange.create(start=anchor(document, _BEATS[3]), beat=quarter, bpm=120)

    coverage: Coverage = _coverage(document=document, context=first)

    expected: set[str] = {item.id for item in (*upper[1:3], *lower[1:3])}
    assert {item.id for item in coverage.notes} == expected


@pytest.mark.unit
def test_a_dynamic_covers_its_voice_until_that_voices_next_dynamic() -> None:
    document, upper, lower = _two_voices()
    first: DynamicChange = DynamicChange.create(
        start=anchor(document, _BEATS[0]),
        voice=document.voices[0],
        dynamic=DynamicMarking.MEZZO_FORTE,
    )
    second: DynamicChange = DynamicChange.create(
        start=anchor(document, _BEATS[0]),
        voice=document.voices[1],
        dynamic=DynamicMarking.MEZZO_FORTE,
    )
    # the first voice gets another dynamic at the third beat: for that voice the first one stops
    # there, for the second voice it goes on
    DynamicChange.create(
        start=anchor(document, _BEATS[2]),
        voice=document.voices[0],
        dynamic=DynamicMarking.FORTE,
    )

    assert {item.id for item in _coverage(document=document, context=first).notes} == {
        item.id for item in upper[:2]
    }
    assert {item.id for item in _coverage(document=document, context=second).notes} == {
        item.id for item in lower
    }
