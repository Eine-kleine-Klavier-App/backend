from collections.abc import Callable
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import Rest, RestCarrier
from piano_app.domain.score.document.models.notation import RhythmicSize, RhythmicValue
from piano_app.domain.score.document.models.structural import Staff
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import iter_leaves
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.engine.postprocessors import (
    FillGapsPostprocessor,
)

from ...scene import (
    Piano,
    Score,
    Slot,
    anchor_at,
    build_engine,
    build_piano,
    build_score,
    delete_entities,
    group,
    group_layout,
    layout,
    note,
    note_at,
    orphan_anchors,
    quarters,
    rest,
    rest_at,
    size,
    slot,
    tie_layout,
    value,
)

# The fill fills holes only (owner, 2026-10-19): each hole of a scope inside one measure is
# placed as one rest item over the whole hole, cut at the barlines and spelled into the
# largest values, on the staff resolved for it. An existing rest is never merged, respelled
# or recreated. Deleting a rest is a normal delete; its hole is filled like any other.

_Q: Fraction = Fraction(1, 4)
_E: Fraction = Fraction(1, 8)
_THIRD: Fraction = Fraction(1, 12)  # one triplet eighth on the timeline


def _score(*, piano: Piano) -> Score:
    return Score(
        document=piano.document, voice=piano.voice, staff=piano.upper, measures=piano.measures
    )


def _rests(*, score: Score) -> list[Rest]:
    return [
        leaf.carrier.rest
        for leaf in iter_leaves(score.voice)
        if isinstance(leaf.carrier, RestCarrier) and leaf.carrier.rest is not None
    ]


def _rests_between_notes(*, piano: Piano) -> Score:
    """A quarter note, a quarter rest on the upper staff, a quarter rest on the lower staff,
    a quarter note."""
    score: Score = _score(piano=piano)
    quarters(score=score, measure=0, beats=(0, 3))
    rest(score=score, parent=score.voice, at=_Q, rhythmic_value=RhythmicValue.QUARTER)
    rest(
        score=score,
        parent=score.voice,
        at=Fraction(1, 2),
        rhythmic_value=RhythmicValue.QUARTER,
        staff=piano.lower,
    )

    return score


# --- a deleted rest's hole is refilled ---------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("deleted", "kept"),
    [
        pytest.param(_Q, Fraction(1, 2), id="left of its neighbour"),
        pytest.param(Fraction(1, 2), _Q, id="right of its neighbour"),
    ],
)
def test_a_deleted_rest_is_refilled_by_a_rest_of_its_size(
    deleted: Fraction,
    kept: Fraction,
) -> None:
    """The hole becomes one new quarter rest on the staff the voice sounds longest on; the
    rest beside it is not merged and keeps its identity and its staff."""
    piano: Piano = build_piano()
    score: Score = _rests_between_notes(piano=piano)
    before: list[Slot] = layout(score=score)
    gone: Rest = rest_at(score=score, at=deleted)
    neighbour: Rest = rest_at(score=score, at=kept)
    neighbour_staff: Staff = neighbour.staff

    delete_entities(score=score, entity_ids=[gone.id])

    assert layout(score=score) == before
    assert rest_at(score=score, at=deleted) is not gone
    assert rest_at(score=score, at=deleted).staff is piano.upper
    assert rest_at(score=score, at=kept) is neighbour
    assert neighbour.staff is neighbour_staff
    assert orphan_anchors(score=score) == []
    assert len(score.measures[0].anchors) == 4


@pytest.mark.unit
@pytest.mark.parametrize("form", ["carrier", "rest and carrier"])
def test_a_rest_named_by_its_carrier_is_refilled_the_same_way(form: str) -> None:
    piano: Piano = build_piano()
    score: Score = _rests_between_notes(piano=piano)
    before: list[Slot] = layout(score=score)
    gone: Rest = rest_at(score=score, at=_Q)
    neighbour: Rest = rest_at(score=score, at=Fraction(1, 2))
    entity_ids: list[str] = [gone.rest_carrier.id]
    if form == "rest and carrier":
        entity_ids.insert(0, gone.id)

    delete_entities(score=score, entity_ids=entity_ids)

    assert layout(score=score) == before
    assert rest_at(score=score, at=_Q) is not gone
    assert rest_at(score=score, at=Fraction(1, 2)) is neighbour


@pytest.mark.unit
def test_deleting_a_rest_rolls_back_to_the_rest_itself() -> None:
    piano: Piano = build_piano()
    score: Score = _rests_between_notes(piano=piano)
    before: list[Slot] = layout(score=score)
    first: Rest = rest_at(score=score, at=_Q)
    second: Rest = rest_at(score=score, at=Fraction(1, 2))

    log: MutationLog = delete_entities(score=score, entity_ids=[first.id])
    log.rollback()

    assert layout(score=score) == before
    assert rest_at(score=score, at=_Q) is first
    assert rest_at(score=score, at=Fraction(1, 2)) is second


# --- rests beside a hole are never merged -------------------------------------------------


@pytest.mark.unit
def test_a_note_deleted_between_two_rests_leaves_three_rests() -> None:
    """The hole is filled with a quarter rest of its own; the rests on either side keep
    their identities, their values and their staffs."""
    piano: Piano = build_piano()
    score: Score = _score(piano=piano)
    quarters(score=score, measure=0, beats=(0, 2))
    rest(score=score, parent=score.voice, at=_Q, rhythmic_value=RhythmicValue.QUARTER)
    rest(
        score=score,
        parent=score.voice,
        at=Fraction(3, 4),
        rhythmic_value=RhythmicValue.QUARTER,
        staff=piano.lower,
    )
    rests_before: list[Rest] = _rests(score=score)

    delete_entities(score=score, entity_ids=[note_at(score=score, at=Fraction(1, 2)).id])

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        *[slot(0, Fraction(beat, 4), _Q, "rest") for beat in range(1, 4)],
    ]
    assert rest_at(score=score, at=_Q) is rests_before[0]
    assert rest_at(score=score, at=Fraction(3, 4)) is rests_before[1]
    assert rests_before[1].staff is piano.lower
    assert orphan_anchors(score=score) == []


def _two_eighths_then_quarters() -> Score:
    """Two eighth notes on beat one, then quarters on beats two to four."""
    score: Score = build_score(measure_count=1)
    note(
        score=score, parent=score.voice, at=Fraction(0), rhythmic_value=RhythmicValue.EIGHTH, step=1
    )
    note(score=score, parent=score.voice, at=_E, rhythmic_value=RhythmicValue.EIGHTH, step=2)
    quarters(score=score, measure=0, beats=(1, 2, 3))

    return score


@pytest.mark.unit
def test_two_adjacent_eighths_deleted_in_one_batch_leave_one_quarter_rest() -> None:
    score: Score = _two_eighths_then_quarters()

    delete_entities(
        score=score,
        entity_ids=[note_at(score=score, at=Fraction(0)).id, note_at(score=score, at=_E).id],
    )

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "rest"),
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_two_adjacent_eighths_deleted_one_per_gesture_leave_two_eighth_rests() -> None:
    """Accepted consequence of filling holes only (owner, 2026-10-19): the first gesture
    fills its hole with an eighth rest, and the second does not merge its hole with that
    rest — so the result differs from deleting both in one batch."""
    score: Score = _two_eighths_then_quarters()

    delete_entities(score=score, entity_ids=[note_at(score=score, at=Fraction(0)).id])
    first: Rest = rest_at(score=score, at=Fraction(0))
    delete_entities(score=score, entity_ids=[note_at(score=score, at=_E).id])

    assert layout(score=score) == [
        slot(0, Fraction(0), _E, "rest"),
        slot(0, _E, _E, "rest"),
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert rest_at(score=score, at=Fraction(0)) is first
    assert orphan_anchors(score=score) == []


# --- a hole across a barline -------------------------------------------------------------


def _rest_across_the_barline_in_a_tuplet(*, piano: Piano) -> Score:
    """Quarters on beats one to three, a quarter triplet sounding [3/4, 5/4) — a quarter
    note, a quarter rest on the lower staff built straight across the barline, a quarter
    note — and quarters on beats two to four of measure two, all other elements above."""
    score: Score = _score(piano=piano)
    quarters(score=score, measure=0, beats=(0, 1, 2))
    triplet: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(3, 4),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
    )
    note(
        score=score,
        parent=triplet,
        at=Fraction(3, 4),
        rhythmic_value=RhythmicValue.QUARTER,
        step=1,
    )
    rest(
        score=score,
        parent=triplet,
        at=Fraction(11, 12),
        rhythmic_value=RhythmicValue.QUARTER,
        staff=piano.lower,
    )
    note(
        score=score,
        parent=triplet,
        at=Fraction(13, 12),
        rhythmic_value=RhythmicValue.QUARTER,
        step=3,
    )
    quarters(score=score, measure=1, beats=(1, 2, 3))

    return score


@pytest.mark.unit
def test_a_hole_across_a_barline_is_cut_there_into_untied_rests() -> None:
    """The rest across the barline goes. Its hole, a written quarter in the triplet, is cut
    at the barline into two eighth rests, untied, on the staff the voice sounds longest on."""
    piano: Piano = build_piano(measure_count=2)
    score: Score = _rest_across_the_barline_in_a_tuplet(piano=piano)

    delete_entities(score=score, entity_ids=[rest_at(score=score, at=Fraction(11, 12)).id])

    assert layout(score=score) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        slot(0, Fraction(3, 4), _Q, "1", depth=1),
        slot(0, Fraction(11, 12), _E, "rest", depth=1),
        slot(1, Fraction(0), _E, "rest", depth=1),
        slot(1, Fraction(1, 12), _Q, "3", depth=1),
        *[slot(1, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert rest_at(score=score, at=Fraction(11, 12)).staff is piano.upper
    assert rest_at(score=score, at=Fraction(1)).staff is piano.upper
    assert tie_layout(score=score) == []
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_hole_beside_a_rest_across_the_barline_leaves_that_rest_alone() -> None:
    """Both notes of the triplet go: each hole is filled with a quarter rest of its own,
    and the rest across the barline keeps its identity and its staff."""
    piano: Piano = build_piano(measure_count=2)
    score: Score = _rest_across_the_barline_in_a_tuplet(piano=piano)
    across: Rest = rest_at(score=score, at=Fraction(11, 12))

    delete_entities(
        score=score,
        entity_ids=[
            note_at(score=score, at=Fraction(3, 4)).id,
            note_at(score=score, at=Fraction(13, 12)).id,
        ],
    )

    assert layout(score=score) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        slot(0, Fraction(3, 4), _Q, "rest", depth=1),
        slot(0, Fraction(11, 12), _Q, "rest", depth=1),
        slot(1, Fraction(1, 12), _Q, "rest", depth=1),
        *[slot(1, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert rest_at(score=score, at=Fraction(11, 12)) is across
    assert across.staff is piano.lower
    assert orphan_anchors(score=score) == []


# --- a hole inside a tuplet --------------------------------------------------------------


def _rest_before_a_triplet_opening_with_a_rest() -> tuple[Score, GroupRhythmicContainer]:
    """A quarter rest, an eighth triplet of a rest and two notes, two quarter notes."""
    score: Score = build_score(measure_count=1)
    rest(score=score, parent=score.voice, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)
    triplet: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=_Q,
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    rest(score=score, parent=triplet, at=_Q, rhythmic_value=RhythmicValue.EIGHTH)
    for index in (1, 2):
        note(
            score=score,
            parent=triplet,
            at=_Q + index * _THIRD,
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index + 1,
        )
    quarters(score=score, measure=0, beats=(2, 3))

    return score, triplet


@pytest.mark.unit
def test_a_hole_inside_a_tuplet_is_filled_in_its_units_beside_its_rest() -> None:
    """The triplet's middle note goes: its hole is one eighth rest written in the triplet's
    units; the triplet's own rest and the rest before the triplet are untouched."""
    score, triplet = _rest_before_a_triplet_opening_with_a_rest()
    rests_before: list[Rest] = _rests(score=score)

    delete_entities(score=score, entity_ids=[note_at(score=score, at=_Q + _THIRD).id])

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "rest"),
        slot(0, _Q, _E, "rest", depth=1),
        slot(0, _Q + _THIRD, _E, "rest", depth=1),
        slot(0, _Q + 2 * _THIRD, _E, "3", depth=1),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert rest_at(score=score, at=Fraction(0)) is rests_before[0]
    assert rest_at(score=score, at=_Q) is rests_before[1]
    assert score.voice.children[1] is triplet
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_deleting_the_last_rest_of_a_tuplet_beside_other_notes_refills_it() -> None:
    """The triplet keeps other notes of its voice around: it stays and its whole interior is
    one hole, filled with one dotted quarter rest."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0, 2, 3))
    triplet: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=_Q,
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    Rest.create(
        rest_carrier=RestCarrier.create(
            owner=LeafRhythmicContainer.create(
                parent=triplet,
                anchor=anchor_at(score=score, at=_Q),
                size=RhythmicSize(value=value(RhythmicValue.QUARTER, 1), count=1),
            )
        ),
        staff=score.staff,
    )
    before: list[Slot] = layout(score=score)
    gone: Rest = rest_at(score=score, at=_Q)

    delete_entities(score=score, entity_ids=[gone.id])

    assert layout(score=score) == before
    assert score.voice.children[1] is triplet
    assert rest_at(score=score, at=_Q) is not gone
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_deleting_the_last_rest_of_a_measure_puts_the_measure_to_sleep() -> None:
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    rest(score=score, parent=score.voice, at=Fraction(1), rhythmic_value=RhythmicValue.WHOLE)

    delete_entities(score=score, entity_ids=[rest_at(score=score, at=Fraction(1)).id])

    assert layout(score=score) == [slot(0, Fraction(beat, 4), _Q, "0") for beat in range(4)]
    assert score.measures[1].anchors == []
    assert group_layout(score=score) == []


# --- the staff of a hole -----------------------------------------------------------------


@pytest.mark.unit
def test_a_hole_beside_a_lower_rest_takes_the_staff_the_voice_sounds_on_longest() -> None:
    """The hole lies next to a rest below, but the voice sounds longer above: the new rest
    goes above, and the rest below stays where it is."""
    piano: Piano = build_piano()
    score: Score = _score(piano=piano)
    quarters(score=score, measure=0, beats=(0, 1, 3))
    rest(
        score=score,
        parent=score.voice,
        at=Fraction(1, 2),
        rhythmic_value=RhythmicValue.QUARTER,
        staff=piano.lower,
    )
    lower: Rest = rest_at(score=score, at=Fraction(1, 2))

    delete_entities(score=score, entity_ids=[note_at(score=score, at=_Q).id])

    assert rest_at(score=score, at=_Q).staff is piano.upper
    assert rest_at(score=score, at=Fraction(1, 2)) is lower
    assert lower.staff is piano.lower


@pytest.mark.unit
def test_a_hole_in_a_measure_sounding_longer_below_goes_below() -> None:
    """Two quarter rests below outweigh the one note left above, so the hole goes below."""
    piano: Piano = build_piano()
    score: Score = _score(piano=piano)
    quarters(score=score, measure=0, beats=(0, 1))
    for at in (Fraction(1, 2), Fraction(3, 4)):
        rest(
            score=score,
            parent=score.voice,
            at=at,
            rhythmic_value=RhythmicValue.QUARTER,
            staff=piano.lower,
        )

    delete_entities(score=score, entity_ids=[note_at(score=score, at=_Q).id])

    assert rest_at(score=score, at=_Q).staff is piano.lower


# --- idempotency -------------------------------------------------------------------------


def _refilled_on_one_level() -> Score:
    score: Score = _rests_between_notes(piano=build_piano())
    delete_entities(score=score, entity_ids=[rest_at(score=score, at=_Q).id])

    return score


def _refilled_across_a_barline() -> Score:
    score: Score = _rest_across_the_barline_in_a_tuplet(piano=build_piano(measure_count=2))
    delete_entities(score=score, entity_ids=[rest_at(score=score, at=Fraction(11, 12)).id])

    return score


def _refilled_inside_a_tuplet() -> Score:
    score, _ = _rest_before_a_triplet_opening_with_a_rest()
    delete_entities(score=score, entity_ids=[note_at(score=score, at=_Q + _THIRD).id])

    return score


@pytest.mark.unit
@pytest.mark.parametrize(
    "refilled",
    [
        pytest.param(_refilled_on_one_level, id="in the voice"),
        pytest.param(_refilled_across_a_barline, id="across a barline"),
        pytest.param(_refilled_inside_a_tuplet, id="inside a tuplet"),
    ],
)
def test_a_second_pass_changes_nothing(refilled: Callable[[], Score]) -> None:
    score: Score = refilled()
    before: list[Slot] = layout(score=score)
    leaves: list[LeafRhythmicContainer] = list(iter_leaves(score.voice))

    assert (
        list(
            FillGapsPostprocessor().search_fixes(
                document=score.document,
                geometry=ScoreGeometry(document=score.document),
            )
        )
        == []
    )

    build_engine().process(document=score.document, requests=[])

    assert layout(score=score) == before
    assert all(kept is leaf for kept, leaf in zip(iter_leaves(score.voice), leaves, strict=True))
    assert orphan_anchors(score=score) == []
