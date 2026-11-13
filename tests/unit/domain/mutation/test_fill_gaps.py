from dataclasses import dataclass
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    RhythmicSize,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    Staff,
    TemporalAnchor,
    Voice,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.postprocessors.fill_gaps import (
    FillGapsPostprocessor,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    PlaceSpansRequest,
)


def _size(value: RhythmicValue, count: int = 1) -> RhythmicSize:
    return RhythmicSize(value=DottedRhythmicValue(value=value), count=count)


@dataclass(frozen=True, slots=True, kw_only=True)
class _Filled:
    """A fill request reduced to what matters: which measure, where, how long (written)."""

    measure_index: int
    position: Fraction
    length: Fraction


def _filled(*, document: ScoreDocument, requests: list[PlaceSpansRequest]) -> list[_Filled]:
    measures: list[Measure] = list(document.measures)

    return sorted(
        (
            _Filled(
                measure_index=measures.index(request.measure),
                position=request.position.value,
                length=request.written_length,
            )
            for request in requests
        ),
        key=lambda filled: (filled.measure_index, filled.position),
    )


def _fill(*, document: ScoreDocument) -> list[_Filled]:
    postprocessor: FillGapsPostprocessor = FillGapsPostprocessor()

    return _filled(
        document=document,
        requests=list(
            postprocessor.search_fixes(document=document, geometry=ScoreGeometry(document=document))
        ),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class _Blank:
    document: ScoreDocument
    voices: list[Voice]
    measures: list[Measure]
    staff: Staff


def _blank(*, voices: int = 1, measure_count: int = 3) -> _Blank:
    measures: list[Measure] = [Measure.create() for _ in range(measure_count)]
    voice_list: list[Voice] = [Voice() for _ in range(voices)]
    staff: Staff = Staff()
    document: ScoreDocument = ScoreDocument.create(
        voices=voice_list, staffs=[staff], measures=measures
    )

    return _Blank(document=document, voices=voice_list, measures=measures, staff=staff)


def _sound(*, leaf: LeafRhythmicContainer, staff: Staff) -> None:
    """Give a leaf a real note. A bare leaf is not a state the engine ever leaves
    behind (cleanup reaps it), and the staff heuristic needs something to look at."""
    Note.create(
        note_carrier=NoteCarrier.create(owner=leaf),
        staff=staff,
        staff_step=0,
        accidental=Accidental.NATURAL,
    )


def _place(
    *,
    blank: _Blank,
    voice: Voice,
    measure: Measure,
    position: Fraction,
    value: RhythmicValue,
) -> LeafRhythmicContainer:
    leaf: LeafRhythmicContainer = LeafRhythmicContainer.create(
        parent=voice,
        anchor=TemporalAnchor.create(
            measure=measure, position=MeasurePosition.of_fraction(fraction=position)
        ),
        size=_size(value),
    )
    _sound(leaf=leaf, staff=blank.staff)

    return leaf


@pytest.mark.unit
def test_a_voice_that_plays_nothing_anywhere_gets_no_rests() -> None:
    """THE sleeping rule. Geometry reports every empty measure as one measure-long hole;
    refusing to fill them is the postprocessor's decision, and losing it would carpet
    every silent measure of every voice with rests."""
    blank: _Blank = _blank(measure_count=3)
    document: ScoreDocument = blank.document

    assert _fill(document=document) == []


@pytest.mark.unit
def test_measures_the_voice_never_reaches_stay_asleep() -> None:
    """One quarter in the first measure wakes THAT measure only — the two after it are still
    silent for this voice and must be left alone."""
    blank: _Blank = _blank(measure_count=3)
    document, voices, measures = blank.document, blank.voices, blank.measures
    _place(
        blank=blank,
        voice=voices[0],
        measure=measures[0],
        position=Fraction(0),
        value=RhythmicValue.QUARTER,
    )

    filled: list[_Filled] = _fill(document=document)

    assert {entry.measure_index for entry in filled} == {0}
    assert sum(entry.length for entry in filled) == Fraction(3, 4)


@pytest.mark.unit
def test_one_voice_waking_a_measure_does_not_wake_the_other() -> None:
    """Sleeping is decided per voice, not per measure — a second voice with nothing in
    the measure stays empty even though the measure itself is busy."""
    blank: _Blank = _blank(voices=2, measure_count=2)
    document, voices, measures = blank.document, blank.voices, blank.measures
    _place(
        blank=blank,
        voice=voices[0],
        measure=measures[0],
        position=Fraction(0),
        value=RhythmicValue.HALF,
    )

    filled: list[_Filled] = _fill(document=document)

    # only the half-note's own measure is tiled, and only for the voice that plays it
    assert filled == [_Filled(measure_index=0, position=Fraction(1, 2), length=Fraction(1, 2))]


@pytest.mark.unit
def test_a_woken_measure_is_tiled_to_its_end() -> None:
    blank: _Blank = _blank(measure_count=2)
    document, voices, measures = blank.document, blank.voices, blank.measures
    _place(
        blank=blank,
        voice=voices[0],
        measure=measures[0],
        position=Fraction(0),
        value=RhythmicValue.QUARTER,
    )
    _place(
        blank=blank,
        voice=voices[0],
        measure=measures[0],
        position=Fraction(1, 2),
        value=RhythmicValue.QUARTER,
    )

    filled: list[_Filled] = _fill(document=document)

    assert filled == [
        _Filled(measure_index=0, position=Fraction(1, 4), length=Fraction(1, 4)),
        _Filled(measure_index=0, position=Fraction(3, 4), length=Fraction(1, 4)),
    ]


@pytest.mark.unit
def test_a_note_spilling_into_the_next_measure_wakes_it() -> None:
    """Waking is about being reached, not about starting there: the remainder of the
    measure a long note runs into still gets tiled."""
    blank: _Blank = _blank(measure_count=3)
    document, voices, measures = blank.document, blank.voices, blank.measures
    _place(
        blank=blank,
        voice=voices[0],
        measure=measures[0],
        position=Fraction(1, 2),
        value=RhythmicValue.WHOLE,
    )

    filled: list[_Filled] = _fill(document=document)

    assert filled == [
        _Filled(measure_index=0, position=Fraction(0), length=Fraction(1, 2)),
        _Filled(measure_index=1, position=Fraction(1, 2), length=Fraction(1, 2)),
    ]


@pytest.mark.unit
def test_an_existing_tuplet_is_always_tiled_in_full() -> None:
    """The deliberate asymmetry: a measure can sleep, a tuplet cannot. Its interior is
    occupied by definition while it exists, so a hole inside it is always filled."""
    blank: _Blank = _blank(measure_count=2)
    document, voices, measures = blank.document, blank.voices, blank.measures

    # the group and its first leaf start at the same instant, so they share one anchor
    start: TemporalAnchor = TemporalAnchor.create(
        measure=measures[0], position=MeasurePosition.of_fraction(fraction=Fraction(1, 4))
    )
    triplet: GroupRhythmicContainer = GroupRhythmicContainer.create(
        parent=voices[0],
        anchor=start,
        written_size=_size(RhythmicValue.EIGHTH, 3),
        occupied_size=_size(RhythmicValue.QUARTER),
    )
    _sound(
        leaf=LeafRhythmicContainer.create(
            parent=triplet,
            anchor=start,
            size=_size(RhythmicValue.EIGHTH),
        ),
        staff=blank.staff,
    )

    filled: list[_Filled] = _fill(document=document)

    # the hole inside the triplet is two written eighths, landing a third of the way
    # into the measure; the measure's own holes sit either side of the triplet
    assert filled == [
        _Filled(measure_index=0, position=Fraction(0), length=Fraction(1, 4)),
        _Filled(measure_index=0, position=Fraction(1, 3), length=Fraction(1, 4)),
        _Filled(measure_index=0, position=Fraction(1, 2), length=Fraction(1, 2)),
    ]


@pytest.mark.unit
def test_a_tuplet_across_the_barline_wakes_and_tiles_both_measures() -> None:
    """Each measure is read on its own, so the tuplet is seen in both: the second measure,
    holding nothing else, wakes for it, and the tuplet's interior is cut at the barline."""
    blank: _Blank = _blank(measure_count=2)
    document, voices, measures = blank.document, blank.voices, blank.measures

    # three quarters in the room of a half, from beat four: its first quarter sounds
    start: TemporalAnchor = TemporalAnchor.create(
        measure=measures[0], position=MeasurePosition.of_fraction(fraction=Fraction(3, 4))
    )
    triplet: GroupRhythmicContainer = GroupRhythmicContainer.create(
        parent=voices[0],
        anchor=start,
        written_size=_size(RhythmicValue.QUARTER, 3),
        occupied_size=_size(RhythmicValue.HALF),
    )
    _sound(
        leaf=LeafRhythmicContainer.create(
            parent=triplet,
            anchor=start,
            size=_size(RhythmicValue.QUARTER),
        ),
        staff=blank.staff,
    )

    filled: list[_Filled] = _fill(document=document)

    # before the tuplet; the written eighth of the tuplet left before the barline, a sixth
    # into its beat; the written dotted quarter after it; the second measure after the tuplet
    assert filled == [
        _Filled(measure_index=0, position=Fraction(0), length=Fraction(3, 4)),
        _Filled(measure_index=0, position=Fraction(11, 12), length=Fraction(1, 8)),
        _Filled(measure_index=1, position=Fraction(0), length=Fraction(3, 8)),
        _Filled(measure_index=1, position=Fraction(1, 4), length=Fraction(3, 4)),
    ]


@pytest.mark.unit
def test_a_note_ending_on_the_barline_does_not_wake_the_next_measure() -> None:
    """A measure is woken by what reaches into it; ending exactly on its barline does not."""
    blank: _Blank = _blank(measure_count=2)
    document, voices, measures = blank.document, blank.voices, blank.measures
    _place(
        blank=blank,
        voice=voices[0],
        measure=measures[0],
        position=Fraction(1, 2),
        value=RhythmicValue.HALF,
    )

    assert _fill(document=document) == [
        _Filled(measure_index=0, position=Fraction(0), length=Fraction(1, 2)),
    ]


@pytest.mark.unit
def test_a_childless_tuplet_alone_wakes_its_measure() -> None:
    """The second measure holds only a tuplet with no children: the tuplet wakes it, so its
    interior and the measure around it are tiled; the third measure stays asleep."""
    blank: _Blank = _blank(measure_count=3)
    document, voices, measures = blank.document, blank.voices, blank.measures
    _place(
        blank=blank,
        voice=voices[0],
        measure=measures[0],
        position=Fraction(0),
        value=RhythmicValue.WHOLE,
    )
    GroupRhythmicContainer.create(
        parent=voices[0],
        anchor=TemporalAnchor.create(
            measure=measures[1], position=MeasurePosition.of_fraction(fraction=Fraction(1, 4))
        ),
        written_size=_size(RhythmicValue.EIGHTH, 3),
        occupied_size=_size(RhythmicValue.QUARTER),
    )

    assert _fill(document=document) == [
        _Filled(measure_index=1, position=Fraction(0), length=Fraction(1, 4)),
        _Filled(measure_index=1, position=Fraction(1, 4), length=Fraction(3, 8)),
        _Filled(measure_index=1, position=Fraction(1, 2), length=Fraction(1, 2)),
    ]


@pytest.mark.unit
def test_a_tuplet_ending_on_the_barline_leaves_the_next_measure_asleep() -> None:
    """A group is tiled up to the last measure it reaches into; ending exactly on a barline,
    it reaches no further, so the measure after gets no segment of it and stays asleep."""
    blank: _Blank = _blank(measure_count=2)
    document, voices, measures = blank.document, blank.voices, blank.measures

    # three eighths in the room of a quarter, on beat four: its first eighth sounds
    start: TemporalAnchor = TemporalAnchor.create(
        measure=measures[0], position=MeasurePosition.of_fraction(fraction=Fraction(3, 4))
    )
    triplet: GroupRhythmicContainer = GroupRhythmicContainer.create(
        parent=voices[0],
        anchor=start,
        written_size=_size(RhythmicValue.EIGHTH, 3),
        occupied_size=_size(RhythmicValue.QUARTER),
    )
    _sound(
        leaf=LeafRhythmicContainer.create(
            parent=triplet,
            anchor=start,
            size=_size(RhythmicValue.EIGHTH),
        ),
        staff=blank.staff,
    )

    assert _fill(document=document) == [
        _Filled(measure_index=0, position=Fraction(0), length=Fraction(3, 4)),
        _Filled(measure_index=0, position=Fraction(5, 6), length=Fraction(1, 4)),
    ]


@pytest.mark.unit
def test_a_tuplet_across_three_measures_fills_the_middle_one_inside_it() -> None:
    """Three wholes in the room of two, from beat three: the middle measure lies wholly inside
    the tuplet, so it gets one full segment of the interior and no hole of the voice."""
    blank: _Blank = _blank(measure_count=3)
    document, voices, measures = blank.document, blank.voices, blank.measures

    # its first written half sounds
    start: TemporalAnchor = TemporalAnchor.create(
        measure=measures[0], position=MeasurePosition.of_fraction(fraction=Fraction(1, 2))
    )
    triplet: GroupRhythmicContainer = GroupRhythmicContainer.create(
        parent=voices[0],
        anchor=start,
        written_size=_size(RhythmicValue.WHOLE, 3),
        occupied_size=_size(RhythmicValue.WHOLE, 2),
    )
    _sound(
        leaf=LeafRhythmicContainer.create(
            parent=triplet,
            anchor=start,
            size=_size(RhythmicValue.HALF),
        ),
        staff=blank.staff,
    )

    # before the tuplet; the written quarter of its interior left in the first measure; the
    # written dotted whole filling the second; the written dotted half in the third and the
    # voice's half after the tuplet
    assert _fill(document=document) == [
        _Filled(measure_index=0, position=Fraction(0), length=Fraction(1, 2)),
        _Filled(measure_index=0, position=Fraction(5, 6), length=Fraction(1, 4)),
        _Filled(measure_index=1, position=Fraction(0), length=Fraction(3, 2)),
        _Filled(measure_index=2, position=Fraction(0), length=Fraction(3, 4)),
        _Filled(measure_index=2, position=Fraction(1, 2), length=Fraction(1, 2)),
    ]


@pytest.mark.unit
def test_a_fully_tiled_measure_needs_nothing() -> None:
    blank: _Blank = _blank(measure_count=2)
    document, voices, measures = blank.document, blank.voices, blank.measures
    _place(
        blank=blank,
        voice=voices[0],
        measure=measures[0],
        position=Fraction(0),
        value=RhythmicValue.WHOLE,
    )

    assert _fill(document=document) == []


@pytest.mark.unit
def test_a_score_with_no_measures_at_all_is_left_alone() -> None:
    document: ScoreDocument = ScoreDocument.create(voices=[Voice()], staffs=[Staff()], measures=[])

    assert _fill(document=document) == []
