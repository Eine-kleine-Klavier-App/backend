from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Note, NoteCarrier, Rest, RestCarrier
from piano_app.domain.score.document.models.notation import Accidental, RhythmicValue
from piano_app.domain.score.document.models.structural import Measure, Staff, Voice
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.geometry import Span
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.postprocessors.fill_gaps import (
    FillGapsPostprocessor,
)
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    CreateRestRequest,
)
from piano_app.domain.score.document.services.resolution import resolve_staff

from ..scene import (
    Score,
    anchor_at,
    build_score,
    delete_entities,
    group,
    insert_note,
    layout,
    note,
    quarters,
    size,
)

# Which staff a rest the fill creates goes on: the staff the voice sounds on longest in
# the gap's bar, notes and rests alike, else the nearest element. Scenes are 4/4 bars on
# two staves.

_Q: Fraction = Fraction(1, 4)
_E: Fraction = Fraction(1, 8)


@dataclass(frozen=True, slots=True, kw_only=True)
class _Piano:
    document: ScoreDocument
    voice: Voice
    upper: Staff
    lower: Staff
    measures: list[Measure]


def _piano(*, bars: int = 1) -> _Piano:
    measures: list[Measure] = [Measure.create() for _ in range(bars)]
    voice: Voice = Voice()
    upper: Staff = Staff()
    lower: Staff = Staff()
    document: ScoreDocument = ScoreDocument.create(
        voices=[voice],
        staffs=[upper, lower],
        measures=measures,
    )

    return _Piano(document=document, voice=voice, upper=upper, lower=lower, measures=measures)


def _score(*, piano: _Piano) -> Score:
    """The same scene seen through the shared builders, for anchors and groups."""
    return Score(
        document=piano.document,
        voice=piano.voice,
        staff=piano.upper,
        measures=piano.measures,
    )


def _leaf(
    *,
    piano: _Piano,
    parent: RhythmicContainerParent,
    at: Fraction,
    rhythmic_value: RhythmicValue,
) -> LeafRhythmicContainer:
    return LeafRhythmicContainer.create(
        parent=parent,
        anchor=anchor_at(score=_score(piano=piano), at=at),
        size=size(rhythmic_value),
    )


def _chord(
    *,
    piano: _Piano,
    at: Fraction,
    rhythmic_value: RhythmicValue,
    staves: Sequence[Staff],
    parent: RhythmicContainerParent | None = None,
) -> None:
    """A chord with one note on each staff listed (a staff listed twice holds two), in the
    voice unless a group is given."""
    carrier: NoteCarrier = NoteCarrier.create(
        owner=_leaf(
            piano=piano,
            parent=piano.voice if parent is None else parent,
            at=at,
            rhythmic_value=rhythmic_value,
        )
    )
    for step, staff in enumerate(staves):
        Note.create(
            note_carrier=carrier,
            staff=staff,
            staff_step=step,
            accidental=Accidental.NATURAL,
        )


def _rest(*, piano: _Piano, at: Fraction, rhythmic_value: RhythmicValue, staff: Staff) -> None:
    Rest.create(
        rest_carrier=RestCarrier.create(
            owner=_leaf(piano=piano, parent=piano.voice, at=at, rhythmic_value=rhythmic_value)
        ),
        staff=staff,
    )


def _filled_staves(*, piano: _Piano) -> list[tuple[Fraction, Staff]]:
    """Every rest the fill would create, as (position on the timeline, staff)."""
    requests: Sequence[CreateRestRequest] = FillGapsPostprocessor().search_fixes(
        document=piano.document
    )

    return sorted(
        (
            (piano.measures.index(request.measure) + request.position.value, request.staff)
            for request in requests
        ),
        key=lambda filled: filled[0],
    )


# --- which staff -------------------------------------------------------------------------


@pytest.mark.unit
def test_a_rest_goes_to_the_staff_the_voice_sounds_on_longest_in_its_bar() -> None:
    """Two quarters above, one below: the rest after the descent still goes above."""
    piano: _Piano = _piano()
    _chord(piano=piano, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, staves=[piano.upper])
    _chord(piano=piano, at=_Q, rhythmic_value=RhythmicValue.QUARTER, staves=[piano.upper])
    _chord(piano=piano, at=2 * _Q, rhythmic_value=RhythmicValue.QUARTER, staves=[piano.lower])

    assert _filled_staves(piano=piano) == [(3 * _Q, piano.upper)]


@pytest.mark.unit
def test_rests_of_the_voice_count_as_much_as_notes() -> None:
    """Two quarter rests the voice holds above outweigh one quarter note below."""
    piano: _Piano = _piano()
    _chord(piano=piano, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, staves=[piano.lower])
    _rest(piano=piano, at=_Q, rhythmic_value=RhythmicValue.QUARTER, staff=piano.upper)
    _rest(piano=piano, at=2 * _Q, rhythmic_value=RhythmicValue.QUARTER, staff=piano.upper)

    assert _filled_staves(piano=piano) == [(3 * _Q, piano.upper)]


@pytest.mark.unit
def test_a_chord_on_two_staves_counts_on_both() -> None:
    """A half chord with notes above and below counts its half on each staff; with a
    quarter below that makes 3/4 below against 1/2 above."""
    piano: _Piano = _piano()
    _chord(
        piano=piano,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.HALF,
        staves=[piano.upper, piano.upper, piano.lower],
    )
    _chord(piano=piano, at=2 * _Q, rhythmic_value=RhythmicValue.QUARTER, staves=[piano.lower])

    assert _filled_staves(piano=piano) == [(3 * _Q, piano.lower)]


@pytest.mark.unit
def test_a_tie_goes_to_the_staff_of_the_element_nearest_the_gap() -> None:
    """A quarter above, a quarter below, a gap between them and one after: equal time
    on both staves. The gap between touches both, so the earlier element decides; the
    gap after touches only the lower one."""
    piano: _Piano = _piano()
    _chord(piano=piano, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, staves=[piano.upper])
    _chord(piano=piano, at=2 * _Q, rhythmic_value=RhythmicValue.QUARTER, staves=[piano.lower])

    assert _filled_staves(piano=piano) == [(_Q, piano.upper), (3 * _Q, piano.lower)]


@pytest.mark.unit
def test_every_rest_of_one_gap_goes_to_the_same_staff() -> None:
    """The 5/8 gap between an eighth above and an eighth below is spelled as a half and an
    eighth rest. The staff is chosen once for the whole gap — a tie, settled by the earlier
    element — so the second rest does not drift to the staff it ends next to."""
    piano: _Piano = _piano()
    _chord(piano=piano, at=Fraction(0), rhythmic_value=RhythmicValue.EIGHTH, staves=[piano.upper])
    _chord(piano=piano, at=6 * _E, rhythmic_value=RhythmicValue.EIGHTH, staves=[piano.lower])

    gap_rests: list[tuple[Fraction, Staff]] = [
        filled for filled in _filled_staves(piano=piano) if filled[0] < 6 * _E
    ]

    assert gap_rests == [(_E, piano.upper), (5 * _E, piano.upper)]


@pytest.mark.unit
def test_a_bar_with_nothing_to_count_takes_the_staff_of_the_nearest_element() -> None:
    """A quarter triplet from beat four with its only note in the next bar, below. The
    first bar holds no element of the voice, so its rests — around the triplet and in its
    empty slots — take the staff of that nearest note."""
    piano: _Piano = _piano(bars=2)
    triplet: GroupRhythmicContainer = GroupRhythmicContainer.create(
        parent=piano.voice,
        anchor=anchor_at(score=_score(piano=piano), at=Fraction(3, 4)),
        written_size=size(RhythmicValue.QUARTER, count=3),
        occupied_size=size(RhythmicValue.HALF),
    )
    _chord(
        piano=piano,
        parent=triplet,
        at=Fraction(13, 12),
        rhythmic_value=RhythmicValue.QUARTER,
        staves=[piano.lower],
    )

    first_bar: list[Staff] = [staff for at, staff in _filled_staves(piano=piano) if at < 1]

    assert first_bar
    assert set(first_bar) == {piano.lower}


@pytest.mark.unit
def test_an_empty_group_is_not_filled() -> None:
    """It is about to be cleaned up; filling it would keep it alive as a tuplet of rests."""
    piano: _Piano = _piano()
    GroupRhythmicContainer.create(
        parent=piano.voice,
        anchor=anchor_at(score=_score(piano=piano), at=Fraction(0)),
        written_size=size(RhythmicValue.EIGHTH, count=3),
        occupied_size=size(RhythmicValue.QUARTER),
    )

    assert _filled_staves(piano=piano) == []


@pytest.mark.unit
def test_a_voice_with_no_element_at_all_is_refused() -> None:
    """Nothing in the voice to take a staff from — deferred, refused for now."""
    piano: _Piano = _piano()
    triplet: GroupRhythmicContainer = GroupRhythmicContainer.create(
        parent=piano.voice,
        anchor=anchor_at(score=_score(piano=piano), at=Fraction(0)),
        written_size=size(RhythmicValue.QUARTER, count=3),
        occupied_size=size(RhythmicValue.HALF),
    )
    rest_leaf: LeafRhythmicContainer = _leaf(
        piano=piano,
        parent=triplet,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.QUARTER,
    )
    RestCarrier.create(owner=rest_leaf)

    with pytest.raises(MutationRejectedError, match="no element to place a rest by"):
        FillGapsPostprocessor().search_fixes(document=piano.document)


# --- empty bars and empty tuplets --------------------------------------------------------


@pytest.mark.unit
def test_a_bar_whose_last_note_is_deleted_keeps_its_rests() -> None:
    """A bar of rests is valid; only an empty bar is left unfilled."""
    score: Score = build_score(bars=1)
    insert_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER)
    leaf = score.voice.children[1]
    assert isinstance(leaf, LeafRhythmicContainer)
    assert isinstance(leaf.carrier, NoteCarrier)

    delete_entities(score=score, entity_ids=[leaf.carrier.id])

    assert [entry.content for entry in layout(score=score)] == ["rest", "rest", "rest"]


@pytest.mark.unit
def test_a_bar_with_notes_left_keeps_its_rests() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)
    leaf = score.voice.children[1]
    assert isinstance(leaf, LeafRhythmicContainer)
    assert isinstance(leaf.carrier, NoteCarrier)

    delete_entities(score=score, entity_ids=[leaf.carrier.id])

    assert [entry.content for entry in layout(score=score)] == ["0", "rest", "0", "0"]


@pytest.mark.unit
def test_rests_keep_a_bar_awake() -> None:
    """A note spilling into the next bar woke it; once the note is gone, its rests stay and
    both bars are tiled with rests."""
    score: Score = build_score(bars=2)
    insert_note(score=score, at=Fraction(3, 4), rhythmic_value=RhythmicValue.HALF)

    carriers: list[str] = []
    for child in score.voice.children:
        if isinstance(child, LeafRhythmicContainer) and isinstance(child.carrier, NoteCarrier):
            carriers.append(child.carrier.id)
    delete_entities(score=score, entity_ids=carriers)

    assert {entry.content for entry in layout(score=score)} == {"rest"}
    assert {entry.measure_index for entry in layout(score=score)} == {0, 1}


@pytest.mark.unit
def test_deleting_every_note_of_a_tuplet_alone_in_its_bar_leaves_the_bar_empty() -> None:
    """A half-note triplet fills the whole bar. All its notes go in one gesture, so it is
    left without children and removed; the bar then holds nothing and is not filled."""
    score: Score = build_score(bars=1)
    triplet: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        written=size(RhythmicValue.HALF, count=3),
        occupied=size(RhythmicValue.WHOLE),
    )
    note_ids: list[str] = []
    for index in range(3):
        leaf: LeafRhythmicContainer = note(
            score=score,
            parent=triplet,
            at=Fraction(index, 3),
            rhythmic_value=RhythmicValue.HALF,
            step=index,
        )
        assert isinstance(leaf.carrier, NoteCarrier)
        note_ids.append(leaf.carrier.notes[0].id)

    delete_entities(score=score, entity_ids=note_ids)

    assert score.voice.children == []
    assert score.measures[0].anchors == []


# --- resolve_staff on its own ------------------------------------------------------------


@pytest.mark.unit
def test_a_gap_past_the_last_measure_has_no_staff() -> None:
    piano: _Piano = _piano()
    _chord(piano=piano, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, staves=[piano.upper])
    geometry: ScoreGeometry = ScoreGeometry(origin=piano.measures[0])

    with pytest.raises(ValueError, match="past the last measure"):
        resolve_staff(
            geometry=geometry,
            voice=piano.voice,
            gap=Span(frame=geometry.root, start=Fraction(1), length=_Q),
        )


@pytest.mark.unit
@pytest.mark.parametrize("upper_first", [True, False])
def test_a_full_tie_settles_on_the_staff_of_the_chords_first_note(upper_first: bool) -> None:
    """One chord, a note on each staff: equal time in the bar, the same nearest element —
    the staff of the chord's first note decides, the same way every run."""
    piano: _Piano = _piano()
    staves: list[Staff] = [piano.upper, piano.lower] if upper_first else [piano.lower, piano.upper]
    _chord(piano=piano, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, staves=staves)
    geometry: ScoreGeometry = ScoreGeometry(origin=piano.measures[0])

    staff: Staff = resolve_staff(
        geometry=geometry,
        voice=piano.voice,
        gap=Span(frame=geometry.root, start=_Q, length=3 * _Q),
    )

    assert staff is staves[0]
