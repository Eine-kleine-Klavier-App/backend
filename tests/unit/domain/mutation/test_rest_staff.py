from collections.abc import Sequence
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import Note, NoteCarrier, Rest, RestCarrier
from piano_app.domain.score.document.models.notation import Accidental, RhythmicValue
from piano_app.domain.score.document.models.structural import Staff
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.geometry import Span
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import iter_leaves
from piano_app.domain.score.document.services.mutation.engine.postprocessors import (
    FillGapsPostprocessor,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    PlaceSpansRequest,
    RestContent,
)
from piano_app.domain.score.document.services.resolution import resolve_staff

from ..scene import (
    Piano,
    Score,
    anchor_at,
    anchor_positions,
    build_engine,
    build_piano,
    build_score,
    delete_entities,
    eighth_triplet,
    group,
    insert_note,
    layout,
    note,
    quarters,
    size,
)

# Which staff a rest the fill creates goes on: the staff the voice sounds on longest in
# the gap's measure, notes and rests alike, else the nearest element. Scenes are 4/4 measures on
# two staffs.

_Q: Fraction = Fraction(1, 4)
_E: Fraction = Fraction(1, 8)


def _score(*, piano: Piano) -> Score:
    """The same scene seen through the shared builders, for anchors and groups."""
    return Score(
        document=piano.document,
        voice=piano.voice,
        staff=piano.upper,
        measures=piano.measures,
    )


def _leaf(
    *,
    piano: Piano,
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
    piano: Piano,
    at: Fraction,
    rhythmic_value: RhythmicValue,
    staffs: Sequence[Staff],
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
    for step, staff in enumerate(staffs):
        Note.create(
            note_carrier=carrier,
            staff=staff,
            staff_step=step,
            accidental=Accidental.NATURAL,
        )


def _rest(*, piano: Piano, at: Fraction, rhythmic_value: RhythmicValue, staff: Staff) -> None:
    Rest.create(
        rest_carrier=RestCarrier.create(
            owner=_leaf(piano=piano, parent=piano.voice, at=at, rhythmic_value=rhythmic_value)
        ),
        staff=staff,
    )


def _rests(*, piano: Piano) -> list[tuple[LeafRhythmicContainer, Rest]]:
    rests: list[tuple[LeafRhythmicContainer, Rest]] = []
    for leaf in iter_leaves(piano.voice):
        if isinstance(leaf.carrier, RestCarrier) and leaf.carrier.rest is not None:
            rests.append((leaf, leaf.carrier.rest))

    return rests


def _filled_staffs(*, piano: Piano) -> list[tuple[Fraction, Staff]]:
    """Every rest the fill creates, as (position on the timeline, staff): a gesture with
    no request runs only the boundary on the scene as it was built. A gap is placed as one
    rest item, so its rests are read from the score once they exist."""
    before: list[Rest] = [rest for _, rest in _rests(piano=piano)]

    build_engine().process(document=piano.document, requests=[])

    geometry: ScoreGeometry = ScoreGeometry(document=piano.document)

    return sorted(
        (
            (geometry.global_span_of(container=leaf).start, rest.staff)
            for leaf, rest in _rests(piano=piano)
            if not any(rest is existing for existing in before)
        ),
        key=lambda filled: filled[0],
    )


# --- which staff -------------------------------------------------------------------------


@pytest.mark.unit
def test_a_rest_goes_to_the_staff_the_voice_sounds_on_longest_in_its_measure() -> None:
    """Two quarters above, one below: the rest after the descent still goes above."""
    piano: Piano = build_piano()
    _chord(piano=piano, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, staffs=[piano.upper])
    _chord(piano=piano, at=_Q, rhythmic_value=RhythmicValue.QUARTER, staffs=[piano.upper])
    _chord(piano=piano, at=2 * _Q, rhythmic_value=RhythmicValue.QUARTER, staffs=[piano.lower])

    assert _filled_staffs(piano=piano) == [(3 * _Q, piano.upper)]


@pytest.mark.unit
def test_rests_of_the_voice_count_as_much_as_notes() -> None:
    """Two quarter rests the voice holds above outweigh one quarter note below."""
    piano: Piano = build_piano()
    _chord(piano=piano, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, staffs=[piano.lower])
    _rest(piano=piano, at=_Q, rhythmic_value=RhythmicValue.QUARTER, staff=piano.upper)
    _rest(piano=piano, at=2 * _Q, rhythmic_value=RhythmicValue.QUARTER, staff=piano.upper)

    assert _filled_staffs(piano=piano) == [(3 * _Q, piano.upper)]


@pytest.mark.unit
def test_a_chord_on_two_staffs_counts_on_both() -> None:
    """A half chord with notes above and below counts its half on each staff; with a
    quarter below that makes 3/4 below against 1/2 above."""
    piano: Piano = build_piano()
    _chord(
        piano=piano,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.HALF,
        staffs=[piano.upper, piano.upper, piano.lower],
    )
    _chord(piano=piano, at=2 * _Q, rhythmic_value=RhythmicValue.QUARTER, staffs=[piano.lower])

    assert _filled_staffs(piano=piano) == [(3 * _Q, piano.lower)]


@pytest.mark.unit
def test_a_tie_goes_to_the_staff_of_the_element_nearest_the_gap() -> None:
    """A quarter above, a quarter below, a gap between them and one after: equal time
    on both staffs. The gap between touches both, so the earlier element decides; the
    gap after touches only the lower one."""
    piano: Piano = build_piano()
    _chord(piano=piano, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, staffs=[piano.upper])
    _chord(piano=piano, at=2 * _Q, rhythmic_value=RhythmicValue.QUARTER, staffs=[piano.lower])

    assert _filled_staffs(piano=piano) == [(_Q, piano.upper), (3 * _Q, piano.lower)]


@pytest.mark.unit
def test_every_rest_of_one_gap_goes_to_the_same_staff() -> None:
    """The 5/8 gap between an eighth above and an eighth below is spelled as a half and an
    eighth rest. The staff is chosen once for the whole gap — a tie, settled by the earlier
    element — so the second rest does not drift to the staff it ends next to."""
    piano: Piano = build_piano()
    _chord(piano=piano, at=Fraction(0), rhythmic_value=RhythmicValue.EIGHTH, staffs=[piano.upper])
    _chord(piano=piano, at=6 * _E, rhythmic_value=RhythmicValue.EIGHTH, staffs=[piano.lower])

    gap_rests: list[tuple[Fraction, Staff]] = [
        filled for filled in _filled_staffs(piano=piano) if filled[0] < 6 * _E
    ]

    assert gap_rests == [(_E, piano.upper), (5 * _E, piano.upper)]


@pytest.mark.unit
def test_a_measure_with_nothing_to_count_takes_the_staff_of_the_nearest_element() -> None:
    """A quarter triplet from beat four with its only note in the next measure, below. The
    first measure holds no element of the voice, so its rests — around the triplet and in its
    empty slots — take the staff of that nearest note."""
    piano: Piano = build_piano(measure_count=2)
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
        staffs=[piano.lower],
    )

    first_measure: list[Staff] = [staff for at, staff in _filled_staffs(piano=piano) if at < 1]

    assert first_measure
    assert set(first_measure) == {piano.lower}


@pytest.mark.unit
def test_a_hole_takes_its_staff_from_an_element_measures_away() -> None:
    """A childless triplet keeps the first measure awake with nothing sounding there. The
    voice's nearest element is a quarter below three measures on, nearer than a quarter above
    two measures after it, so every rest the fill places in the first measure goes below.
    The fill is asked directly: in a gesture the triplet would be removed first."""
    piano: Piano = build_piano(measure_count=6)
    group(
        score=_score(piano=piano),
        parent=piano.voice,
        at=_Q,
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    _chord(piano=piano, at=Fraction(3), rhythmic_value=RhythmicValue.QUARTER, staffs=[piano.lower])
    _chord(piano=piano, at=Fraction(5), rhythmic_value=RhythmicValue.QUARTER, staffs=[piano.upper])

    fixes: Sequence[PlaceSpansRequest] = FillGapsPostprocessor().search_fixes(
        document=piano.document,
        geometry=ScoreGeometry(document=piano.document),
    )
    first_measure: list[bool] = [
        isinstance(fix.content, RestContent) and fix.content.staff is piano.lower
        for fix in fixes
        if fix.measure is piano.measures[0]
    ]

    # around the triplet, and its whole interior
    assert first_measure == [True, True, True]


@pytest.mark.unit
def test_an_empty_group_is_not_filled() -> None:
    """It is about to be cleaned up; filling it would keep it alive as a tuplet of rests."""
    piano: Piano = build_piano()
    GroupRhythmicContainer.create(
        parent=piano.voice,
        anchor=anchor_at(score=_score(piano=piano), at=Fraction(0)),
        written_size=size(RhythmicValue.EIGHTH, count=3),
        occupied_size=size(RhythmicValue.QUARTER),
    )

    assert _filled_staffs(piano=piano) == []


@pytest.mark.unit
def test_a_voice_with_no_element_at_all_has_no_staff() -> None:
    """Nothing in the voice to take a staff from. The fill never asks for it — rests go
    only where a note or rest already is — so this is a guard on the function itself."""
    piano: Piano = build_piano()
    geometry: ScoreGeometry = ScoreGeometry(document=piano.document)

    with pytest.raises(ValueError, match="no element to place a rest by"):
        resolve_staff(
            geometry=geometry,
            voice=piano.voice,
            gap=Span(frame=geometry.root, start=Fraction(0), length=_Q),
        )


@pytest.mark.unit
def test_a_measure_whose_last_note_is_deleted_keeps_its_rests() -> None:
    """A measure of rests is valid; only an empty measure is left unfilled."""
    score: Score = build_score(measure_count=1)
    insert_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER)
    leaf = score.voice.children[1]
    assert isinstance(leaf, LeafRhythmicContainer)
    assert isinstance(leaf.carrier, NoteCarrier)

    delete_entities(score=score, entity_ids=[leaf.carrier.id])

    assert [entry.content for entry in layout(score=score)] == ["rest", "rest", "rest"]


@pytest.mark.unit
def test_a_measure_with_notes_left_keeps_its_rests() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    leaf = score.voice.children[1]
    assert isinstance(leaf, LeafRhythmicContainer)
    assert isinstance(leaf.carrier, NoteCarrier)

    delete_entities(score=score, entity_ids=[leaf.carrier.id])

    assert [entry.content for entry in layout(score=score)] == ["0", "rest", "0", "0"]


@pytest.mark.unit
def test_rests_keep_a_measure_awake() -> None:
    """A note spilling into the next measure woke it; once the note is gone, its rests stay and
    both measures are tiled with rests."""
    score: Score = build_score(measure_count=2)
    insert_note(score=score, at=Fraction(3, 4), rhythmic_value=RhythmicValue.HALF)

    carriers: list[str] = []
    for child in score.voice.children:
        if isinstance(child, LeafRhythmicContainer) and isinstance(child.carrier, NoteCarrier):
            carriers.append(child.carrier.id)
    delete_entities(score=score, entity_ids=carriers)

    assert {entry.content for entry in layout(score=score)} == {"rest"}
    assert {entry.measure_index for entry in layout(score=score)} == {0, 1}


@pytest.mark.unit
def test_deleting_every_note_of_a_tuplet_alone_in_its_measure_leaves_the_measure_empty() -> None:
    """A half-note triplet fills the whole measure. All its notes go in one gesture, so it is
    left without children with nothing else of its voice in its measure and is removed; the
    measure then holds nothing and is not filled."""
    score: Score = build_score(measure_count=1)
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
    assert anchor_positions(score.measures[0]) == [Fraction(0)]


# --- resolve_staff on its own ------------------------------------------------------------


@pytest.mark.unit
def test_a_gap_past_the_last_measure_has_no_staff() -> None:
    piano: Piano = build_piano()
    _chord(piano=piano, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, staffs=[piano.upper])
    geometry: ScoreGeometry = ScoreGeometry(document=piano.document)

    with pytest.raises(ValueError, match="past the last measure"):
        resolve_staff(
            geometry=geometry,
            voice=piano.voice,
            gap=Span(frame=geometry.root, start=Fraction(1), length=_Q),
        )


@pytest.mark.unit
@pytest.mark.parametrize("upper_first", [True, False])
def test_a_full_tie_settles_on_the_staff_the_voice_meets_first(upper_first: bool) -> None:
    """One chord, a note on each staff: equal time in the measure, the same nearest element —
    the staff the voice meets first decides, the same way every run. The chord is all the
    voice holds, so that is the staff of its first note."""
    piano: Piano = build_piano()
    staffs: list[Staff] = [piano.upper, piano.lower] if upper_first else [piano.lower, piano.upper]
    _chord(piano=piano, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, staffs=staffs)
    geometry: ScoreGeometry = ScoreGeometry(document=piano.document)

    staff: Staff = resolve_staff(
        geometry=geometry,
        voice=piano.voice,
        gap=Span(frame=geometry.root, start=_Q, length=3 * _Q),
    )

    assert staff is staffs[0]


# --- the empty-voice refusal is unreachable ----------------------------------------------
# A rest is created only where a note or a rest already is (in the measure, or inside the
# group), so the staff always has something to come from. These are the paths that used to
# reach the refusal through mid-gesture scaffolding: a leaf whose carrier is gone.


@pytest.mark.unit
def test_deleting_a_note_and_its_neighbours_carrier_together_empties_the_measure() -> None:
    score: Score = build_score(measure_count=1)
    first: LeafRhythmicContainer = note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.HALF,
        step=1,
    )
    second: LeafRhythmicContainer = note(
        score=score,
        parent=score.voice,
        at=Fraction(1, 2),
        rhythmic_value=RhythmicValue.HALF,
        step=2,
    )
    assert isinstance(first.carrier, NoteCarrier)
    assert isinstance(second.carrier, NoteCarrier)

    delete_entities(score=score, entity_ids=[first.carrier.notes[0].id, second.carrier.id])

    assert score.voice.children == []
    assert anchor_positions(score.measures[0]) == [Fraction(0)]


@pytest.mark.unit
def test_a_mixed_delete_of_a_whole_tuplet_alone_in_its_measure_empties_the_measure() -> None:
    score: Score = build_score(measure_count=1)
    triplet: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        written=size(RhythmicValue.HALF, count=3),
        occupied=size(RhythmicValue.WHOLE),
    )
    carriers: list[NoteCarrier] = []
    for index in range(3):
        leaf: LeafRhythmicContainer = note(
            score=score,
            parent=triplet,
            at=Fraction(index, 3),
            rhythmic_value=RhythmicValue.HALF,
            step=index,
        )
        assert isinstance(leaf.carrier, NoteCarrier)
        carriers.append(leaf.carrier)

    delete_entities(
        score=score,
        entity_ids=[carriers[0].notes[0].id, carriers[1].id, carriers[2].id],
    )

    assert score.voice.children == []
    assert anchor_positions(score.measures[0]) == [Fraction(0)]


@pytest.mark.unit
def test_a_mixed_delete_of_a_whole_tuplet_beside_other_notes_keeps_it_tiled() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    triplet: GroupRhythmicContainer = eighth_triplet(score=score, parent=score.voice, at=_Q)
    quarters(score=score, measure=0, beats=(2, 3))
    carriers: list[NoteCarrier] = []
    for child in triplet.children:
        assert isinstance(child, LeafRhythmicContainer)
        assert isinstance(child.carrier, NoteCarrier)
        carriers.append(child.carrier)

    delete_entities(
        score=score,
        entity_ids=[carriers[0].notes[0].id, carriers[1].id, carriers[2].id],
    )

    assert [entry.content for entry in layout(score=score)] == ["0", "rest", "0", "0"]
    assert layout(score=score)[1].depth == 1
    assert score.voice.children[1] is triplet
