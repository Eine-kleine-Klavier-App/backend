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
    RhythmicContainer,
)
from piano_app.domain.score.document.services.geometry import Span
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import RhythmicSizeMapper
from piano_app.domain.score.document.services.mutation import build_compiler
from piano_app.domain.score.document.services.mutation.compiler import (
    CreateTupletWithNoteIntent,
    CreateTupletWithRestIntent,
    DeleteBatchIntent,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.intent import (
    RemoveAnalyzer,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.engine.typing import MutationWorkItem
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.intent import (
    RemoveRequest,
)

from ..scene import (
    NEW_STEP,
    GroupSlot,
    Score,
    Slot,
    build_engine,
    build_score,
    delete_entities,
    eighth_triplet,
    group,
    group_layout,
    insert_note,
    layout,
    note,
    orphan_anchors,
    quarters,
    size,
    slot,
    tie_pairs,
    value,
    with_start_contexts,
)

_Q: Fraction = Fraction(1, 4)
_E: Fraction = Fraction(1, 8)
_THIRD: Fraction = Fraction(1, 12)  # one eighth of an eighth triplet on the timeline


def _first_value(*, written: RhythmicSize) -> DottedRhythmicValue:
    """The first value the tuplet's interior is spelled into — a first rest of that length
    leaves the tuplet laid out exactly as the fill alone would lay it out."""
    return RhythmicSizeMapper().spell_duration(duration=written.fraction)[0]


def _create_tuplet(
    *,
    score: Score,
    at: Fraction,
    written: RhythmicSize,
    occupied: RhythmicSize,
    first: DottedRhythmicValue | None = None,
) -> MutationLog:
    """A tuplet created with its first rest — by default as long as the first value its
    interior is spelled into. A tuplet crossing a barline names a first rest that ends at
    or before the barline, so no first rest is cut there.

    The fill never touches the first rest: it keeps its value, and each hole left in the
    tuplet is filled with a rest item of its own.
    """
    intent: CreateTupletWithRestIntent = CreateTupletWithRestIntent(
        voice_id=score.voice.id,
        staff_id=score.staff.id,
        measure_id=score.measures[int(at)].id,
        position=MeasurePosition.of_fraction(fraction=at - int(at)),
        written_size=written,
        occupied_size=occupied,
        written_value=_first_value(written=written) if first is None else first,
    )

    return build_engine().process(
        document=score.document,
        requests=build_compiler().compile(document=score.document, intent=intent),
    )


def _eighth_triplet_at(*, score: Score, at: Fraction) -> MutationLog:
    return _create_tuplet(
        score=score,
        at=at,
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )


def _groups(*, score: Score) -> list[GroupRhythmicContainer]:
    """Every group of the voice, outer before inner, in timeline order."""
    groups: list[GroupRhythmicContainer] = []
    pending: list[RhythmicContainer] = list(reversed(score.voice.children))
    while pending:
        container: RhythmicContainer = pending.pop()
        if isinstance(container, GroupRhythmicContainer):
            groups.append(container)
            pending.extend(reversed(container.children))

    return groups


def _assert_tuplet(
    *,
    score: Score,
    tuplet: GroupRhythmicContainer,
    starts_at: Fraction,
    lasts: Fraction,
) -> None:
    """The tuplet sounds over [starts_at, starts_at + lasts) of the timeline and its
    interior is tiled exactly to its written size."""
    span: Span = ScoreGeometry(document=score.document).global_span_of(container=tuplet)

    assert (span.start, span.length) == (starts_at, lasts)
    assert (
        sum((child.occupied_size.fraction for child in tuplet.children), Fraction(0))
        == tuplet.written_size.fraction
    )


def _assert_refused(
    *,
    score: Score,
    at: Fraction,
    written: RhythmicSize,
    occupied: RhythmicSize,
    message: str,
) -> None:
    """The tuplet is refused and the score comes out exactly as it went in."""
    before: list[Slot] = layout(score=score)
    groups: list[GroupSlot] = group_layout(score=score)
    anchors: int = sum(len(measure.anchors) for measure in score.measures)

    with pytest.raises(MutationRejectedError, match=message):
        _create_tuplet(score=score, at=at, written=written, occupied=occupied)

    assert layout(score=score) == before
    assert group_layout(score=score) == groups
    assert sum(len(measure.anchors) for measure in score.measures) == anchors


def _triplet_scene() -> tuple[Score, GroupRhythmicContainer]:
    """A quarter, an eighth triplet on beat two (staff steps 1, 2, 3), two quarters."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    triplet: GroupRhythmicContainer = eighth_triplet(score=score, parent=score.voice, at=_Q)
    quarters(score=score, measure=0, beats=(2, 3))

    return score, triplet


def _six_eight_measure() -> Score:
    """One 6/8 measure of six eighths."""
    measures: list[Measure] = [Measure.create(time_signature=size(RhythmicValue.EIGHTH, count=6))]
    voice: Voice = Voice()
    staff: Staff = Staff()
    score: Score = Score(
        document=with_start_contexts(
            ScoreDocument.create(voices=[voice], staffs=[staff], measures=measures)
        ),
        voice=voice,
        staff=staff,
        measures=measures,
    )
    for index in range(6):
        note(
            score=score,
            parent=voice,
            at=Fraction(index, 8),
            rhythmic_value=RhythmicValue.EIGHTH,
            step=0,
        )

    return score


# --- creating -----------------------------------------------------------------------------


@pytest.mark.unit
def test_a_new_tuplet_displaces_the_note_it_covers() -> None:
    """Created with a first rest as long as its whole interior, written in its own units:
    a dotted quarter in a triplet of eighths, sounding a quarter."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)

    _eighth_triplet_at(score=score, at=_Q)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, Fraction(3, 8), "rest", depth=1),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_new_tuplet_displaces_a_longer_note_whole() -> None:
    """A half under a quarter-long tuplet goes as a whole; what it leaves past the tuplet
    becomes a rest of the voice."""
    score: Score = build_score(measure_count=1)
    for beat in (0, 2):
        note(
            score=score,
            parent=score.voice,
            at=Fraction(beat, 4),
            rhythmic_value=RhythmicValue.HALF,
            step=0,
        )

    _eighth_triplet_at(score=score, at=Fraction(0))

    assert layout(score=score) == [
        slot(0, Fraction(0), Fraction(3, 8), "rest", depth=1),
        slot(0, _Q, _Q, "rest"),
        slot(0, Fraction(1, 2), Fraction(1, 2), "0"),
    ]


@pytest.mark.unit
def test_a_tuplet_starting_on_another_groups_first_instant_is_nested_in_it() -> None:
    """Half-open like a note: the start belongs to the group, so a sixteenth triplet there
    takes the room of the outer triplet's first eighth."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    outer: GroupRhythmicContainer = eighth_triplet(score=score, parent=score.voice, at=_Q)
    quarters(score=score, measure=0, beats=(2, 3))

    _create_tuplet(
        score=score,
        at=_Q,
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
    )

    assert layout(score=score)[1:4] == [
        slot(0, _Q, Fraction(3, 16), "rest", depth=2),
        slot(0, _Q + _THIRD, _E, "2", depth=1),
        slot(0, _Q + 2 * _THIRD, _E, "3", depth=1),
    ]
    inner = outer.children[0]
    assert isinstance(inner, GroupRhythmicContainer)
    assert inner.start_anchor is outer.start_anchor


@pytest.mark.unit
def test_a_tuplet_may_cross_a_barline() -> None:
    """A quarter triplet from beat four takes a half: the rest of the first measure and the
    first beat of the next, displacing a quarter in each."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1)

    _create_tuplet(
        score=score,
        at=Fraction(3, 4),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
        first=value(RhythmicValue.QUARTER),
    )

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "0"),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "rest", depth=1),
        slot(0, Fraction(11, 12), _E, "rest", depth=1),
        slot(1, Fraction(0), Fraction(3, 8), "rest", depth=1),
        slot(1, _Q, _Q, "0"),
        slot(1, Fraction(1, 2), _Q, "0"),
        slot(1, Fraction(3, 4), _Q, "0"),
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_tuplet_wakes_a_sleeping_measure_of_its_voice() -> None:
    """The voice reaches the measure through the tuplet and its first element, so the rest of
    the measure is tiled too."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)

    _eighth_triplet_at(score=score, at=Fraction(5, 4))

    assert layout(score=score)[4:] == [
        slot(1, Fraction(0), _Q, "rest"),
        slot(1, _Q, Fraction(3, 8), "rest", depth=1),
        slot(1, Fraction(1, 2), Fraction(1, 2), "rest"),
    ]


@pytest.mark.unit
def test_notes_go_into_a_created_tuplet_by_the_ordinary_insert() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    _eighth_triplet_at(score=score, at=_Q)

    insert_note(score=score, at=_Q, rhythmic_value=RhythmicValue.EIGHTH)
    insert_note(score=score, at=_Q + 2 * _THIRD, rhythmic_value=RhythmicValue.EIGHTH, step=7)

    assert layout(score=score)[1:4] == [
        slot(0, _Q, _E, str(NEW_STEP), depth=1),
        slot(0, _Q + _THIRD, _E, "rest", depth=1),
        slot(0, _Q + 2 * _THIRD, _E, "7", depth=1),
    ]


@pytest.mark.unit
def test_creating_a_tuplet_is_one_gesture_and_rolls_back_as_one() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    before: list[Slot] = layout(score=score)

    log: MutationLog = _eighth_triplet_at(score=score, at=_Q)
    log.rollback()

    assert layout(score=score) == before
    assert len(score.measures[0].anchors) == 4


# --- refusals -------------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("at", "written", "occupied", "message"),
    [
        # 5/4 in a 4/4 measure is a wrong address
        (
            Fraction(5, 4),
            size(RhythmicValue.EIGHTH, count=3),
            size(RhythmicValue.QUARTER),
            "at or past the end of the measure",
        ),
        # a half-long tuplet from beat four of the last measure runs off the score
        (
            Fraction(3, 4),
            size(RhythmicValue.QUARTER, count=3),
            size(RhythmicValue.HALF),
            "does not fit in its scope",
        ),
        # three quarters in the time of three quarters scale nothing
        (
            Fraction(0),
            size(RhythmicValue.QUARTER, count=3),
            size(RhythmicValue.QUARTER, count=3),
            "differ in written and occupied size",
        ),
    ],
)
def test_a_refused_tuplet_leaves_the_score_untouched(
    at: Fraction,
    written: RhythmicSize,
    occupied: RhythmicSize,
    message: str,
) -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    before: list[Slot] = layout(score=score)

    with pytest.raises(MutationRejectedError, match=message):
        build_engine().process(
            document=score.document,
            requests=build_compiler().compile(
                document=score.document,
                intent=CreateTupletWithRestIntent(
                    voice_id=score.voice.id,
                    staff_id=score.staff.id,
                    measure_id=score.measures[0].id,
                    position=MeasurePosition.of_fraction(fraction=at),
                    written_size=written,
                    occupied_size=occupied,
                    written_value=_first_value(written=written),
                ),
            ),
        )

    assert layout(score=score) == before


@pytest.mark.unit
def test_a_tuplet_tearing_out_of_the_group_it_starts_in_is_refused() -> None:
    """From the triplet's third eighth only one written eighth is left; a tuplet taking a
    quarter there does not fit."""
    score: Score = build_score(measure_count=1)
    eighth_triplet(score=score, parent=score.voice, at=Fraction(0))
    quarters(score=score, measure=0, beats=(1, 2, 3))

    with pytest.raises(MutationRejectedError, match="does not fit in its scope"):
        _create_tuplet(
            score=score,
            at=2 * _THIRD,
            written=size(RhythmicValue.EIGHTH, count=3),
            occupied=size(RhythmicValue.QUARTER),
        )


# --- deleting a tuplet through the batch ----------------------------------------------------


def _first_note_id(*, leaf: LeafRhythmicContainer) -> str:
    assert isinstance(leaf.carrier, NoteCarrier)
    return leaf.carrier.notes[0].id


@pytest.mark.unit
def test_a_deleted_tuplet_gives_its_room_back_to_the_voice() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    triplet: GroupRhythmicContainer = eighth_triplet(score=score, parent=score.voice, at=_Q)
    quarters(score=score, measure=0, beats=(2, 3))
    start: TemporalAnchor = triplet.start_anchor

    delete_entities(score=score, entity_ids=[triplet.id])

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "rest"),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert score.measures[0].anchors[1] is start
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_what_a_listed_tuplet_holds_is_left_to_its_cascade() -> None:
    """A note, a carrier and a nested group inside a listed tuplet are pruned; the batch's
    remove request deletes the outermost listed group only, ahead of anything else
    listed. Read off its analyzer with no engine: nothing executes, so nothing is
    skipped."""
    score: Score = build_score(measure_count=1)
    outer: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    inner: GroupRhythmicContainer = group(
        score=score,
        parent=outer,
        at=Fraction(0),
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
    )
    deep: LeafRhythmicContainer = note(
        score=score,
        parent=inner,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.SIXTEENTH,
        step=1,
    )
    shallow: LeafRhythmicContainer = note(
        score=score,
        parent=outer,
        at=_THIRD,
        rhythmic_value=RhythmicValue.EIGHTH,
        step=2,
    )
    outside: LeafRhythmicContainer = note(
        score=score,
        parent=score.voice,
        at=_Q,
        rhythmic_value=RhythmicValue.QUARTER,
        step=3,
    )
    assert isinstance(shallow.carrier, NoteCarrier)

    compiled: list[MutationRequest] = list(
        build_compiler().compile(
            document=score.document,
            intent=DeleteBatchIntent(
                entity_ids=(
                    _first_note_id(leaf=deep),
                    shallow.carrier.id,
                    inner.id,
                    _first_note_id(leaf=outside),
                    outer.id,
                )
            ),
        )
    )

    assert len(compiled) == 1
    remove: MutationRequest = compiled[0]
    assert isinstance(remove, RemoveRequest)
    requests: list[MutationWorkItem] = list(
        RemoveAnalyzer().analyze(request=remove, geometry=ScoreGeometry(document=score.document))
    )

    assert requests[0] == DeleteRequest(target=outer)
    assert len(requests) == 2
    assert not any(
        isinstance(request, DeleteRequest) and request.target is inner for request in requests
    )


# --- sizes ----------------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("written", "occupied", "rests"),
    [
        # a triplet: three in the time of two
        (size(RhythmicValue.EIGHTH, count=3), size(RhythmicValue.QUARTER), [Fraction(3, 8)]),
        # a quintuplet's 5/16 is no single value: a quarter and a sixteenth
        (
            size(RhythmicValue.SIXTEENTH, count=5),
            size(RhythmicValue.QUARTER),
            [Fraction(1, 4), Fraction(1, 16)],
        ),
        (size(RhythmicValue.SIXTEENTH, count=6), size(RhythmicValue.QUARTER), [Fraction(3, 8)]),
        # a septuplet's 7/16 is one double-dotted quarter
        (size(RhythmicValue.SIXTEENTH, count=7), size(RhythmicValue.QUARTER), [Fraction(7, 16)]),
    ],
)
def test_tuplets_of_every_ratio_in_four_four_take_one_beat_and_are_tiled(
    written: RhythmicSize,
    occupied: RhythmicSize,
    rests: list[Fraction],
) -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)

    _create_tuplet(score=score, at=Fraction(0), written=written, occupied=occupied)

    tuplets: list[GroupRhythmicContainer] = _groups(score=score)
    assert len(tuplets) == 1
    _assert_tuplet(score=score, tuplet=tuplets[0], starts_at=Fraction(0), lasts=occupied.fraction)
    assert [entry.written for entry in layout(score=score) if entry.depth == 1] == rests
    assert [entry.content for entry in layout(score=score) if entry.depth == 0] == ["0"] * 3


@pytest.mark.unit
def test_a_quarter_triplet_takes_half_a_measure() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)

    _create_tuplet(
        score=score,
        at=Fraction(0),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
    )

    _assert_tuplet(
        score=score,
        tuplet=_groups(score=score)[0],
        starts_at=Fraction(0),
        lasts=Fraction(1, 2),
    )
    assert [entry.content for entry in layout(score=score)] == ["rest", "0", "0"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("count", "rest"),
    [
        (2, Fraction(1, 4)),  # a duplet stretches two eighths over three
        (4, Fraction(1, 2)),  # a quadruplet squeezes four eighths into three
    ],
)
def test_duplets_and_quadruplets_in_six_eight_take_half_the_measure(
    count: int,
    rest: Fraction,
) -> None:
    score: Score = _six_eight_measure()

    _create_tuplet(
        score=score,
        at=Fraction(0),
        written=size(RhythmicValue.EIGHTH, count=count),
        occupied=size(RhythmicValue.EIGHTH, count=3),
    )

    _assert_tuplet(
        score=score,
        tuplet=_groups(score=score)[0],
        starts_at=Fraction(0),
        lasts=Fraction(3, 8),
    )
    assert layout(score=score) == [
        slot(0, Fraction(0), rest, "rest", depth=1),
        slot(0, Fraction(3, 8), _E, "0"),
        slot(0, Fraction(1, 2), _E, "0"),
        slot(0, Fraction(5, 8), _E, "0"),
    ]


# --- position in the measure --------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("beat", [0, 1, 2, 3])
def test_a_tuplet_on_any_beat_replaces_exactly_that_beat(beat: int) -> None:
    """On the last beat it ends exactly on the barline."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)

    _eighth_triplet_at(score=score, at=Fraction(beat, 4))

    _assert_tuplet(
        score=score,
        tuplet=_groups(score=score)[0],
        starts_at=Fraction(beat, 4),
        lasts=_Q,
    )
    contents: list[str] = ["0", "0", "0", "0"]
    contents[beat] = "rest"
    assert [entry.content for entry in layout(score=score)] == contents
    assert [entry.depth for entry in layout(score=score)].count(1) == 1


@pytest.mark.unit
def test_an_offbeat_tuplet_displaces_both_beats_it_touches_and_rests_fill_the_rest() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)

    _eighth_triplet_at(score=score, at=_E)

    assert layout(score=score) == [
        slot(0, Fraction(0), _E, "rest"),
        slot(0, _E, Fraction(3, 8), "rest", depth=1),
        slot(0, Fraction(3, 8), _E, "rest"),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]


@pytest.mark.unit
def test_two_tuplets_side_by_side_keep_their_own_room() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)

    _eighth_triplet_at(score=score, at=Fraction(0))
    _eighth_triplet_at(score=score, at=_Q)

    first, second = _groups(score=score)
    _assert_tuplet(score=score, tuplet=first, starts_at=Fraction(0), lasts=_Q)
    _assert_tuplet(score=score, tuplet=second, starts_at=_Q, lasts=_Q)
    assert [entry.content for entry in layout(score=score)] == ["rest", "rest", "0", "0"]


# --- across barlines ------------------------------------------------------------------------


@pytest.mark.unit
def test_a_tuplet_across_a_barline_displaces_a_long_note_before_it_whole() -> None:
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(0, 1))
    note(
        score=score,
        parent=score.voice,
        at=Fraction(1, 2),
        rhythmic_value=RhythmicValue.HALF,
        step=0,
    )
    quarters(score=score, measure=1)

    _create_tuplet(
        score=score,
        at=Fraction(3, 4),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
        first=value(RhythmicValue.QUARTER),
    )

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "0"),
        slot(0, Fraction(1, 2), _Q, "rest"),
        slot(0, Fraction(3, 4), _Q, "rest", depth=1),
        slot(0, Fraction(11, 12), _E, "rest", depth=1),
        slot(1, Fraction(0), Fraction(3, 8), "rest", depth=1),
        slot(1, _Q, _Q, "0"),
        slot(1, Fraction(1, 2), _Q, "0"),
        slot(1, Fraction(3, 4), _Q, "0"),
    ]


@pytest.mark.unit
def test_a_tuplet_across_two_barlines() -> None:
    """Three wholes in the time of two from the middle of the first measure reach the middle
    of the third. Its interior is tiled measure by measure in its own units: its first rest,
    a dotted half, fills its part of the first measure; a dotted whole rest fills the second
    and a dotted half rest its part of the third."""
    score: Score = build_score(measure_count=3)
    for measure in range(3):
        quarters(score=score, measure=measure)

    _create_tuplet(
        score=score,
        at=Fraction(1, 2),
        written=size(RhythmicValue.WHOLE, count=3),
        occupied=size(RhythmicValue.WHOLE, count=2),
        first=value(RhythmicValue.HALF, 1),
    )

    _assert_tuplet(
        score=score,
        tuplet=_groups(score=score)[0],
        starts_at=Fraction(1, 2),
        lasts=Fraction(2),
    )
    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "0"),
        slot(0, Fraction(1, 2), Fraction(3, 4), "rest", depth=1),
        slot(1, Fraction(0), Fraction(3, 2), "rest", depth=1),
        slot(2, Fraction(0), Fraction(3, 4), "rest", depth=1),
        slot(2, Fraction(1, 2), _Q, "0"),
        slot(2, Fraction(3, 4), _Q, "0"),
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_tuplet_running_into_a_sleeping_measure_wakes_it() -> None:
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)

    _create_tuplet(
        score=score,
        at=Fraction(3, 4),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
        first=value(RhythmicValue.QUARTER),
    )

    assert layout(score=score)[3:] == [
        slot(0, Fraction(3, 4), _Q, "rest", depth=1),
        slot(0, Fraction(11, 12), _E, "rest", depth=1),
        slot(1, Fraction(0), Fraction(3, 8), "rest", depth=1),
        slot(1, _Q, Fraction(3, 4), "rest"),
    ]


@pytest.mark.unit
def test_a_tuplet_starting_on_a_barline_belongs_to_the_next_measure() -> None:
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1)

    _eighth_triplet_at(score=score, at=Fraction(1))

    tuplet: GroupRhythmicContainer = _groups(score=score)[0]
    assert tuplet.start_anchor.measure is score.measures[1]
    assert tuplet.start_anchor.position.value == 0
    assert [entry.content for entry in layout(score=score)[:4]] == ["0"] * 4


@pytest.mark.unit
def test_a_tuplet_ending_exactly_on_the_last_barline_fits() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)

    _create_tuplet(
        score=score,
        at=Fraction(1, 2),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
    )

    _assert_tuplet(
        score=score,
        tuplet=_groups(score=score)[0],
        starts_at=Fraction(1, 2),
        lasts=Fraction(1, 2),
    )


@pytest.mark.unit
def test_a_tuplet_ending_a_sliver_past_the_last_barline_is_refused() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)

    _assert_refused(
        score=score,
        at=Fraction(1, 2) + Fraction(1, 32),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
        message="does not fit in its scope",
    )


@pytest.mark.unit
def test_a_note_inserted_into_a_tuplet_across_a_barline_is_cut_and_tied_inside_it() -> None:
    """A written half from the triplet's second quarter: the barline falls 1/8 written
    in, so it becomes an eighth before it and a dotted quarter after, both in the group."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1)
    _create_tuplet(
        score=score,
        at=Fraction(3, 4),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
        first=value(RhythmicValue.QUARTER),
    )

    insert_note(score=score, at=Fraction(3, 4) + Fraction(1, 6), rhythmic_value=RhythmicValue.HALF)

    assert layout(score=score)[3:6] == [
        slot(0, Fraction(3, 4), _Q, "rest", depth=1),
        slot(0, Fraction(11, 12), _E, str(NEW_STEP), depth=1),
        slot(1, Fraction(0), Fraction(3, 8), str(NEW_STEP), depth=1),
    ]
    assert tie_pairs(score=score) == [(NEW_STEP, NEW_STEP)]


# --- nesting --------------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("slot_index", "kept"),
    [
        (0, ["2", "3"]),
        (1, ["1", "3"]),
        (2, ["1", "2"]),
    ],
)
def test_a_tuplet_in_any_slot_of_a_triplet_replaces_only_that_slot(
    slot_index: int,
    kept: list[str],
) -> None:
    score, outer = _triplet_scene()

    _create_tuplet(
        score=score,
        at=_Q + slot_index * _THIRD,
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
    )

    inner: GroupRhythmicContainer = _groups(score=score)[1]
    assert inner.parent is outer
    _assert_tuplet(score=score, tuplet=inner, starts_at=_Q + slot_index * _THIRD, lasts=_THIRD)
    _assert_tuplet(score=score, tuplet=outer, starts_at=_Q, lasts=_Q)
    assert [entry.content for entry in layout(score=score) if entry.depth == 1] == kept


@pytest.mark.unit
def test_a_nested_tuplet_may_take_exactly_the_rest_of_its_group() -> None:
    """From the second slot a quarter (in the triplet's units) runs to the triplet's last
    instant: it fits and replaces both remaining notes."""
    score, outer = _triplet_scene()

    _create_tuplet(
        score=score,
        at=_Q + _THIRD,
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )

    inner: GroupRhythmicContainer = _groups(score=score)[1]
    _assert_tuplet(score=score, tuplet=inner, starts_at=_Q + _THIRD, lasts=2 * _THIRD)
    assert [child.start_anchor.position.value for child in outer.children] == [_Q, _Q + _THIRD]


@pytest.mark.unit
def test_tuplets_nest_three_deep_and_share_one_anchor() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)

    _eighth_triplet_at(score=score, at=Fraction(0))
    _create_tuplet(
        score=score,
        at=Fraction(0),
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
    )
    _create_tuplet(
        score=score,
        at=Fraction(0),
        written=size(RhythmicValue.THIRTY_SECOND, count=3),
        occupied=size(RhythmicValue.SIXTEENTH),
    )

    outer, middle, inner = _groups(score=score)
    assert inner.parent is middle and middle.parent is outer
    assert inner.start_anchor is middle.start_anchor is outer.start_anchor
    _assert_tuplet(score=score, tuplet=outer, starts_at=Fraction(0), lasts=_Q)
    _assert_tuplet(score=score, tuplet=middle, starts_at=Fraction(0), lasts=_THIRD)
    _assert_tuplet(score=score, tuplet=inner, starts_at=Fraction(0), lasts=Fraction(1, 36))


@pytest.mark.unit
def test_a_nested_tuplet_may_cross_the_barline_its_group_crosses() -> None:
    """In a quarter triplet from beat four, an eighth triplet in its second quarter starts
    at 11/12 and ends at 1/12 of the next measure."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1)
    _create_tuplet(
        score=score,
        at=Fraction(3, 4),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
        first=value(RhythmicValue.QUARTER),
    )

    _create_tuplet(
        score=score,
        at=Fraction(11, 12),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
        first=value(RhythmicValue.EIGHTH),
    )

    outer, inner = _groups(score=score)
    assert inner.parent is outer
    _assert_tuplet(score=score, tuplet=inner, starts_at=Fraction(11, 12), lasts=Fraction(1, 6))
    _assert_tuplet(score=score, tuplet=outer, starts_at=Fraction(3, 4), lasts=Fraction(1, 2))


@pytest.mark.unit
def test_a_voice_level_tuplet_partly_covering_a_group_displaces_the_group_whole() -> None:
    score, triplet = _triplet_scene()

    _eighth_triplet_at(score=score, at=_E)

    assert triplet not in _groups(score=score)
    assert layout(score=score) == [
        slot(0, Fraction(0), _E, "rest"),
        slot(0, _E, Fraction(3, 8), "rest", depth=1),
        slot(0, Fraction(3, 8), _E, "rest"),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]


@pytest.mark.unit
def test_a_tuplet_on_a_groups_first_instant_nests_rather_than_replaces() -> None:
    """The start belongs to the group, so the same ratio there is a tuplet inside the
    triplet's first slot — replacing the triplet itself means deleting it first."""
    score, triplet = _triplet_scene()

    _create_tuplet(
        score=score,
        at=_Q,
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
    )

    assert _groups(score=score)[0] is triplet
    assert _groups(score=score)[1].parent is triplet


# --- a tuplet may not leave the tuplet it starts in -----------------------------------------


@pytest.mark.unit
def test_from_a_middle_slot_a_tuplet_longer_than_what_is_left_is_refused() -> None:
    """Two written eighths are left from the second slot; three do not fit."""
    score, _triplet = _triplet_scene()

    _assert_refused(
        score=score,
        at=_Q + _THIRD,
        written=size(RhythmicValue.SIXTEENTH, count=5),
        occupied=size(RhythmicValue.EIGHTH, count=3),
        message="does not fit in its scope",
    )


@pytest.mark.unit
def test_from_a_groups_start_a_tuplet_longer_than_the_group_is_refused() -> None:
    score, _triplet = _triplet_scene()

    _assert_refused(
        score=score,
        at=_Q,
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.HALF),
        message="does not fit in its scope",
    )


@pytest.mark.unit
def test_a_tuplet_fitting_the_outer_group_but_not_the_inner_one_is_refused() -> None:
    """At the shared start the innermost group is the scope: a quarter fits the outer
    triplet's 3/8 but not the inner sixteenth triplet's 3/16."""
    score, outer = _triplet_scene()
    _create_tuplet(
        score=score,
        at=_Q,
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
    )

    _assert_refused(
        score=score,
        at=_Q,
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
        message="does not fit in its scope",
    )
    assert len(outer.children) == 3


@pytest.mark.unit
def test_a_tuplet_past_the_end_of_a_group_across_a_barline_is_refused() -> None:
    """The quarter triplet from beat four ends at 1/4 of the next measure; from its third
    quarter only one written quarter is left."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1)
    _create_tuplet(
        score=score,
        at=Fraction(3, 4),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
        first=value(RhythmicValue.QUARTER),
    )

    _assert_refused(
        score=score,
        at=1 + Fraction(1, 12),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
        message="does not fit in its scope",
    )


@pytest.mark.unit
def test_a_nested_tuplet_that_scales_nothing_is_refused() -> None:
    score, _triplet = _triplet_scene()

    _assert_refused(
        score=score,
        at=_Q,
        written=size(RhythmicValue.SIXTEENTH, count=2),
        occupied=size(RhythmicValue.EIGHTH),
        message="differ in written and occupied size",
    )


# --- interaction with content -----------------------------------------------------------------


@pytest.mark.unit
def test_a_tuplet_over_a_tied_note_takes_the_tie_with_the_note() -> None:
    score: Score = build_score(measure_count=2)
    insert_note(score=score, at=Fraction(3, 4), rhythmic_value=RhythmicValue.HALF)
    assert tie_pairs(score=score) == [(NEW_STEP, NEW_STEP)]

    _eighth_triplet_at(score=score, at=Fraction(1))

    assert tie_pairs(score=score) == []
    assert layout(score=score)[1] == slot(0, Fraction(3, 4), _Q, str(NEW_STEP))


@pytest.mark.unit
def test_a_tuplet_over_a_chord_displaces_every_note_of_it() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    insert_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER)

    _eighth_triplet_at(score=score, at=_Q)

    steps: list[int] = [
        item.staff_step for item in score.staff.musical_items if isinstance(item, Note)
    ]
    assert NEW_STEP not in steps
    assert len(steps) == 3


@pytest.mark.unit
def test_a_tuplet_in_one_voice_leaves_another_voice_alone() -> None:
    measures: list[Measure] = [Measure.create()]
    upper: Voice = Voice()
    lower: Voice = Voice()
    staff: Staff = Staff()
    document: ScoreDocument = with_start_contexts(
        ScoreDocument.create(
            voices=[upper, lower],
            staffs=[staff],
            measures=measures,
        )
    )
    score: Score = Score(document=document, voice=upper, staff=staff, measures=measures)
    other: Score = Score(document=document, voice=lower, staff=staff, measures=measures)
    quarters(score=score, measure=0)
    quarters(score=other, measure=0)
    before: list[Slot] = layout(score=other)

    _eighth_triplet_at(score=score, at=_Q)

    assert layout(score=other) == before
    assert len(_groups(score=score)) == 1


@pytest.mark.unit
def test_a_tuplet_naming_a_measure_as_its_voice_is_refused() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)

    with pytest.raises(MutationRejectedError, match="must be Voice"):
        build_compiler().compile(
            document=score.document,
            intent=CreateTupletWithRestIntent(
                voice_id=score.measures[0].id,
                staff_id=score.staff.id,
                measure_id=score.measures[0].id,
                position=MeasurePosition.of_fraction(fraction=Fraction(0)),
                written_size=size(RhythmicValue.EIGHTH, count=3),
                occupied_size=size(RhythmicValue.QUARTER),
                written_value=value(RhythmicValue.EIGHTH),
            ),
        )


# --- deleting and rolling back --------------------------------------------------------------


@pytest.mark.unit
def test_deleting_only_a_nested_tuplet_leaves_a_rest_in_its_slot_of_the_outer_one() -> None:
    score, outer = _triplet_scene()
    _create_tuplet(
        score=score,
        at=_Q + _THIRD,
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
    )
    inner: GroupRhythmicContainer = _groups(score=score)[1]

    delete_entities(score=score, entity_ids=[inner.id])

    assert _groups(score=score) == [outer]
    assert layout(score=score)[1:4] == [
        slot(0, _Q, _E, "1", depth=1),
        slot(0, _Q + _THIRD, _E, "rest", depth=1),
        slot(0, _Q + 2 * _THIRD, _E, "3", depth=1),
    ]


@pytest.mark.unit
def test_deleting_a_tuplet_across_a_barline_rests_both_measures_and_reaps_its_anchors() -> None:
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1)
    _create_tuplet(
        score=score,
        at=Fraction(3, 4),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
        first=value(RhythmicValue.QUARTER),
    )
    insert_note(
        score=score, at=Fraction(3, 4) + Fraction(1, 3), rhythmic_value=RhythmicValue.QUARTER
    )

    delete_entities(score=score, entity_ids=[_groups(score=score)[0].id])

    assert layout(score=score)[3:5] == [
        slot(0, Fraction(3, 4), _Q, "rest"),
        slot(1, Fraction(0), _Q, "rest"),
    ]
    assert orphan_anchors(score=score) == []
    assert [len(measure.anchors) for measure in score.measures] == [4, 4]


@pytest.mark.unit
def test_rolling_back_a_nested_tuplet_restores_the_outer_one() -> None:
    score, outer = _triplet_scene()
    before: list[Slot] = layout(score=score)

    log: MutationLog = _create_tuplet(
        score=score,
        at=_Q + _THIRD,
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
    )
    log.rollback()

    assert layout(score=score) == before
    assert _groups(score=score) == [outer]


@pytest.mark.unit
def test_rolling_back_a_tuplet_across_a_barline_restores_both_measures() -> None:
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1)
    before: list[Slot] = layout(score=score)

    log: MutationLog = _create_tuplet(
        score=score,
        at=Fraction(3, 4),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
        first=value(RhythmicValue.QUARTER),
    )
    log.rollback()

    assert layout(score=score) == before
    assert [len(measure.anchors) for measure in score.measures] == [4, 4]


# --- the first element ------------------------------------------------------------------------


def _with_note(
    *,
    score: Score,
    at: Fraction,
    written: RhythmicSize,
    occupied: RhythmicSize,
    rhythmic_value: RhythmicValue,
) -> MutationLog:
    intent: CreateTupletWithNoteIntent = CreateTupletWithNoteIntent(
        voice_id=score.voice.id,
        staff_id=score.staff.id,
        measure_id=score.measures[int(at)].id,
        position=MeasurePosition.of_fraction(fraction=at - int(at)),
        written_size=written,
        occupied_size=occupied,
        written_value=value(rhythmic_value),
        staff_step=NEW_STEP,
        accidental=Accidental.NATURAL,
    )

    return build_engine().process(
        document=score.document,
        requests=build_compiler().compile(document=score.document, intent=intent),
    )


@pytest.mark.unit
def test_a_tuplet_starts_with_the_note_it_is_created_with() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)

    _with_note(
        score=score,
        at=_Q,
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
        rhythmic_value=RhythmicValue.EIGHTH,
    )

    assert layout(score=score)[1:3] == [
        slot(0, _Q, _E, str(NEW_STEP), depth=1),
        slot(0, _Q + _THIRD, _Q, "rest", depth=1),
    ]


@pytest.mark.unit
def test_a_tuplet_starts_with_the_rest_it_is_created_with() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)

    _create_tuplet(
        score=score,
        at=_Q,
        written=size(RhythmicValue.SIXTEENTH, count=5),
        occupied=size(RhythmicValue.QUARTER),
    )

    tuplet: GroupRhythmicContainer = _groups(score=score)[0]
    first = tuplet.children[0]
    assert isinstance(first, LeafRhythmicContainer)
    assert first.written_size.fraction == _Q
    assert layout(score=score)[1:3] == [
        slot(0, _Q, _Q, "rest", depth=1),
        slot(0, _Q + Fraction(1, 5), Fraction(1, 16), "rest", depth=1),
    ]


@pytest.mark.unit
def test_a_first_element_longer_than_the_tuplet_is_refused() -> None:
    """A written half does not fit an eighth triplet's three written eighths."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    before: list[Slot] = layout(score=score)

    with pytest.raises(MutationRejectedError, match="does not fit in its scope"):
        _with_note(
            score=score,
            at=Fraction(0),
            written=size(RhythmicValue.EIGHTH, count=3),
            occupied=size(RhythmicValue.QUARTER),
            rhythmic_value=RhythmicValue.HALF,
        )

    assert layout(score=score) == before


@pytest.mark.unit
def test_a_first_element_crossing_a_barline_is_cut_inside_the_tuplet() -> None:
    """In a quarter triplet from beat four a written half sounds a third and runs past the
    barline: the tuplet is created first, then the half is cut at the barline inside it
    (3/8 | 1/8 written) and its pieces are tied (tuplet-creation, 2026-10-18)."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1)

    _with_note(
        score=score,
        at=Fraction(3, 4),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
        rhythmic_value=RhythmicValue.HALF,
    )

    assert layout(score=score)[3:6] == [
        slot(0, Fraction(3, 4), Fraction(3, 8), str(NEW_STEP), depth=1),
        slot(1, Fraction(0), _E, str(NEW_STEP), depth=1),
        slot(1, Fraction(1, 12), _Q, "rest", depth=1),
    ]
    assert tie_pairs(score=score) == [(NEW_STEP, NEW_STEP)]


@pytest.mark.unit
def test_a_tuplet_and_its_first_note_are_one_gesture() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    before: list[Slot] = layout(score=score)

    log: MutationLog = _with_note(
        score=score,
        at=_Q,
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
        rhythmic_value=RhythmicValue.EIGHTH,
    )
    log.rollback()

    assert layout(score=score) == before
    assert _groups(score=score) == []
