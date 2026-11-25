from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.context import (
    ClefChange,
    Context,
    DynamicChange,
    Hairpin,
    KeySignatureChange,
    Slur,
)
from piano_app.domain.score.document.models.material import Carrier, Note
from piano_app.domain.score.document.models.notation import (
    Clef,
    DynamicMarking,
    GlissandoType,
    RhythmicSize,
    RhythmicValue,
)
from piano_app.domain.score.document.models.relations import Beam, Glissando
from piano_app.domain.score.document.models.structural import (
    MEASURE_START,
    Measure,
    MeasurePosition,
    TemporalAnchor,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    RhythmicContainer,
)
from piano_app.domain.score.document.services.helpers import find_beams
from piano_app.domain.score.document.services.mutation.compiler import (
    DeleteBatchIntent,
    EditIntent,
    TieNotesIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)

from ...scene import (
    ContextSlot,
    Piano,
    Score,
    Snapshot,
    anchor_at,
    anchor_layout,
    anchor_positions,
    apply_intent,
    build_piano,
    build_score,
    build_score_with,
    build_two_voices,
    context_layout,
    crossing_triplet,
    four_quarters,
    group,
    group_spans,
    layout,
    note,
    note_at,
    numbered_quarters,
    orphan_anchors,
    own_contexts,
    pending,
    planned_intent,
    quarters,
    refresh_score,
    signatures,
    size,
    slot,
    snapshot,
    tie_layout,
)

# Measure operations (measure-operations): a new measure takes its left neighbour's time
# signature, or its right neighbour's when inserted before the first. Contexts are left
# alone (their ends are anchored by measure + position); a tie or glissando a new measure lands
# in the middle of is removed and a beam is cut into the runs on either side (relation-guard);
# a tuplet crossing the insertion point is split in two (same ratio, each part's written size
# following its share of the time). Removing a measure removes its elements with their ties
# and the inner part of a tuplet crossing its boundary; a beam through it closes up over it.
# The last measure is never removed.
#
# Contexts when a measure is removed (owner, 2026-10-19): a point context or a span context's
# start standing in it moves right to the start of the following measure; a span context's end
# standing in it moves left to that same boundary when it is after the context's start, else
# the context is removed. When the removed measure is the last one, its point contexts and the
# span contexts ending in it are removed.
#
# A scene position reads "measure index + position inside the measure"; ``note_at`` reads
# the timeline from the score's start, which differs only in the 3/4 scenes.

_Q: Fraction = Fraction(1, 4)
_H: Fraction = Fraction(1, 2)
_E: Fraction = Fraction(1, 8)
_SIXTH: Fraction = Fraction(1, 12)  # one sextuplet eighth, one quarter-triplet eighth
_THREE_FOUR: RhythmicSize = size(RhythmicValue.QUARTER, count=3)
_FOUR_FOUR: RhythmicSize = size(RhythmicValue.QUARTER, count=4)
# the refusal message for the last measure is not decided; it is only expected to name it
_LAST_MEASURE: str = r"(?i)measure"

_PENDING = pending(stage=5)


def append_measure() -> EditIntent:
    """``AppendMeasureIntent()``: no fields, the new measure goes after the last one."""
    return planned_intent("AppendMeasureIntent")


def insert_measure(*, before: Measure) -> EditIntent:
    """``InsertMeasureIntent(before_measure_id)``: the new measure goes right before it.

    The same intent inserts between two measures and before the first.
    """
    return planned_intent("InsertMeasureIntent", before_measure_id=before.id)


def remove_measure(*, measure: Measure) -> EditIntent:
    """``RemoveMeasureIntent(measure_id)``."""
    return planned_intent("RemoveMeasureIntent", measure_id=measure.id)


def _tie(*, score: Score, start_at: Fraction, end_at: Fraction) -> None:
    """Tie the notes starting at two timeline positions."""
    apply_intent(
        score=score,
        intent=TieNotesIntent(
            start_note_id=note_at(score=score, at=start_at).id,
            end_note_id=note_at(score=score, at=end_at).id,
        ),
    )


def _sextuplet_across_the_barline() -> Score:
    score: Score = build_score(measure_count=2)
    _add_sextuplet_across_the_barline(score=score)

    return score


def _add_sextuplet_across_the_barline(*, score: Score) -> None:
    """Add six eighths in the time of a half from beat four, three on each side of the barline.

    Quarters fill beats one to three of measure one and beats two to four of measure two;
    the eighths are on staff steps 1-6.
    """
    quarters(score=score, measure=0, beats=(0, 1, 2))
    sextuplet: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(3, 4),
        written=size(RhythmicValue.EIGHTH, count=6),
        occupied=size(RhythmicValue.HALF),
    )
    for index in range(6):
        note(
            score=score,
            parent=sextuplet,
            at=Fraction(3, 4) + index * _SIXTH,
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index + 1,
        )
    quarters(score=score, measure=1, beats=(1, 2, 3))


def _nested_tuplets_across(*, score: Score, barline: int) -> None:
    """Add nested tuplets crossing the barline at the start of measure ``barline``.

    Quarters fill beats one and two of the measure before. Three halves in the time of a
    whole (staff steps 1 and 6 on their halves) run from beat three over the barline; inside
    them three quarters in the time of a half run from 5/6 of that measure, holding q e | e q
    (staff steps 2-5) cut at the barline. Beats three and four after it are left to the
    scene.
    """
    start: int = barline - 1
    quarters(score=score, measure=start, beats=(0, 1))
    outer: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=start + _H,
        written=size(RhythmicValue.HALF, count=3),
        occupied=size(RhythmicValue.WHOLE),
    )
    note(score=score, parent=outer, at=start + _H, rhythmic_value=RhythmicValue.HALF, step=1)
    inner: GroupRhythmicContainer = group(
        score=score,
        parent=outer,
        at=start + Fraction(5, 6),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
    )
    for at, rhythmic_value, step in (
        (Fraction(5, 6), RhythmicValue.QUARTER, 2),
        (Fraction(17, 18), RhythmicValue.EIGHTH, 3),
        (Fraction(1), RhythmicValue.EIGHTH, 4),
        (Fraction(19, 18), RhythmicValue.QUARTER, 5),
    ):
        note(score=score, parent=inner, at=start + at, rhythmic_value=rhythmic_value, step=step)
    note(
        score=score,
        parent=outer,
        at=start + Fraction(7, 6),
        rhythmic_value=RhythmicValue.HALF,
        step=6,
    )


@pytest.mark.unit
@_PENDING
def test_an_appended_measure_takes_the_last_measures_signature_and_sleeps() -> None:
    """The new measure is 3/4 like the last one and gets no rests; nothing else changes."""
    score: Score = build_score_with(time_signatures=[_FOUR_FOUR, _THREE_FOUR])
    quarters(score=score, measure=0)
    quarters(score=score, measure=1, beats=(0, 1, 2))
    before: Snapshot = snapshot(score=score)

    apply_intent(score=score, intent=append_measure())

    after: Score = refresh_score(score=score)
    assert after.measures[:2] == score.measures
    assert signatures(score=after) == [Fraction(1), Fraction(3, 4), Fraction(3, 4)]
    assert list(after.measures[2].anchors) == []
    assert snapshot(score=after) == before


@pytest.mark.unit
@_PENDING
def test_a_measure_inserted_between_two_takes_the_left_signature_and_breaks_the_tie() -> None:
    """A 3/4 measure goes between a 3/4 and a 4/4 measure and sleeps.

    It lands in the middle of the tie across the barline, which is removed; the slur over
    the barline keeps both its anchors, so it now stretches over the new measure.
    """
    score: Score = build_score_with(time_signatures=[_THREE_FOUR, _FOUR_FOUR])
    quarters(score=score, measure=0, beats=(0, 1))
    note(score=score, parent=score.voice, at=_H, rhythmic_value=RhythmicValue.QUARTER, step=1)
    note(
        score=score,
        parent=score.voice,
        at=Fraction(1),
        rhythmic_value=RhythmicValue.QUARTER,
        step=1,
    )
    quarters(score=score, measure=1, beats=(1, 2, 3))
    _tie(score=score, start_at=_H, end_at=Fraction(3, 4))
    slur_end: TemporalAnchor = anchor_at(score=score, at=1 + _Q)
    slur: Slur = Slur.create(
        start=anchor_at(score=score, at=Fraction(0)),
        end=slur_end,
        voice=score.voice,
    )

    apply_intent(score=score, intent=insert_measure(before=score.measures[1]))

    after: Score = refresh_score(score=score)
    assert [after.measures[0], after.measures[2]] == score.measures
    assert signatures(score=after) == [Fraction(3, 4), Fraction(3, 4), Fraction(1)]
    assert layout(score=after) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "0"),
        slot(0, _H, _Q, "1"),
        slot(2, Fraction(0), _Q, "1"),
        *[slot(2, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert tie_layout(score=after) == []
    assert group_spans(score=after) == []
    assert context_layout(score=after) == [("Slur", (0, Fraction(0)), (2, _Q))]
    assert slur.end is slur_end
    assert anchor_layout(score=after) == [
        (0, Fraction(0)),
        (0, _Q),
        (0, _H),
        *[(2, Fraction(beat, 4)) for beat in range(4)],
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_a_measure_inserted_before_the_first_takes_the_right_signature() -> None:
    score: Score = build_score_with(time_signatures=[_THREE_FOUR, _FOUR_FOUR])
    quarters(score=score, measure=0, beats=(0, 1, 2))
    quarters(score=score, measure=1)

    apply_intent(score=score, intent=insert_measure(before=score.measures[0]))

    after: Score = refresh_score(score=score)
    assert after.measures[1:] == score.measures
    assert signatures(score=after) == [Fraction(3, 4), Fraction(3, 4), Fraction(1)]
    assert layout(score=after) == [
        *[slot(1, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        *[slot(2, Fraction(beat, 4), _Q, "0") for beat in range(4)],
    ]
    assert anchor_positions(after.measures[0]) == [Fraction(0)]
    assert anchor_layout(score=after) == [
        (0, Fraction(0)),
        *[(1, Fraction(beat, 4)) for beat in range(3)],
        *[(2, Fraction(beat, 4)) for beat in range(4)],
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_a_glissando_a_new_measure_lands_in_the_middle_of_is_removed() -> None:
    score: Score = build_score(measure_count=2)
    numbered_quarters(score=score, measure=0, first_step=1)
    numbered_quarters(score=score, measure=1, first_step=5)
    start: Note = note_at(score=score, at=Fraction(3, 4))
    end: Note = note_at(score=score, at=Fraction(1))
    Glissando.create(start_note=start, end_note=end, glissando_type=GlissandoType.WAVY)

    apply_intent(score=score, intent=insert_measure(before=score.measures[1]))

    after: Score = refresh_score(score=score)
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, str(1 + beat)) for beat in range(4)],
        *[slot(2, Fraction(beat, 4), _Q, str(5 + beat)) for beat in range(4)],
    ]
    assert (list(start.relations), list(end.relations)) == ([], [])
    assert anchor_layout(score=after) == [
        (measure, Fraction(beat, 4)) for measure in (0, 2) for beat in range(4)
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_a_measure_inserted_inside_a_tuplet_across_the_barline_splits_it_in_two() -> None:
    """A new measure at the barline splits the sextuplet over it into two tuplets of the same ratio.

    Each side becomes three eighths in the time of a quarter; the new measure sleeps between
    them.
    """
    score: Score = _sextuplet_across_the_barline()

    apply_intent(score=score, intent=insert_measure(before=score.measures[1]))

    after: Score = refresh_score(score=score)
    assert signatures(score=after) == [Fraction(1), Fraction(1), Fraction(1)]
    assert group_spans(score=after) == [
        (0, Fraction(3, 4), Fraction(3, 8), _Q, 0),
        (2, Fraction(0), Fraction(3, 8), _Q, 0),
    ]
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        *[
            slot(0, Fraction(3, 4) + index * _SIXTH, _E, str(1 + index), depth=1)
            for index in range(3)
        ],
        *[slot(2, index * _SIXTH, _E, str(4 + index), depth=1) for index in range(3)],
        *[slot(2, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert tie_layout(score=after) == []
    assert anchor_layout(score=after) == [
        *[(0, Fraction(beat, 4)) for beat in range(4)],
        (0, Fraction(5, 6)),
        (0, Fraction(11, 12)),
        *[(2, index * _SIXTH) for index in range(3)],
        *[(2, Fraction(beat, 4)) for beat in range(1, 4)],
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_inserting_at_a_crossing_triplets_barline_splits_it_and_drops_the_tie() -> None:
    """The quarter triplet [3/4, 5/4) is split at the barline the new measure lands on.

    Each part keeps the ratio over a quarter; the middle quarter's pieces stay in their
    parts, and the tie between them, which the new measure lands in the middle of, goes.
    """
    score: Score = crossing_triplet()

    apply_intent(score=score, intent=insert_measure(before=score.measures[1]))

    after: Score = refresh_score(score=score)
    assert signatures(score=after) == [Fraction(1), Fraction(1), Fraction(1)]
    assert group_spans(score=after) == [
        (0, Fraction(3, 4), Fraction(3, 8), _Q, 0),
        (2, Fraction(0), Fraction(3, 8), _Q, 0),
    ]
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        slot(0, Fraction(3, 4), _Q, "1", depth=1),
        slot(0, Fraction(11, 12), _E, "2", depth=1),
        slot(2, Fraction(0), _E, "2", depth=1),
        slot(2, _SIXTH, _Q, "3", depth=1),
        *[slot(2, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert tie_layout(score=after) == []
    assert list(after.measures[1].anchors) == []
    assert anchor_layout(score=after) == [
        *[(0, Fraction(beat, 4)) for beat in range(4)],
        (0, Fraction(11, 12)),
        (2, Fraction(0)),
        (2, _SIXTH),
        *[(2, Fraction(beat, 4)) for beat in range(1, 4)],
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_removing_a_measure_removes_its_elements_and_the_ties_through_it() -> None:
    """Measure two goes with its notes; the ties into and out of it go, their outer notes stay."""
    score: Score = build_score(measure_count=3)
    quarters(score=score, measure=0, beats=(0, 1, 2))
    for at, step in ((Fraction(3, 4), 1), (Fraction(1), 1), (Fraction(7, 4), 2), (Fraction(2), 2)):
        note(
            score=score, parent=score.voice, at=at, rhythmic_value=RhythmicValue.QUARTER, step=step
        )
    quarters(score=score, measure=1, beats=(1, 2))
    quarters(score=score, measure=2, beats=(1, 2, 3))
    _tie(score=score, start_at=Fraction(3, 4), end_at=Fraction(1))
    _tie(score=score, start_at=Fraction(7, 4), end_at=Fraction(2))
    before_tied: Note = note_at(score=score, at=Fraction(3, 4))
    after_tied: Note = note_at(score=score, at=Fraction(2))

    apply_intent(score=score, intent=remove_measure(measure=score.measures[1]))

    after: Score = refresh_score(score=score)
    assert after.measures == [score.measures[0], score.measures[2]]
    assert signatures(score=after) == [Fraction(1), Fraction(1)]
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        slot(0, Fraction(3, 4), _Q, "1"),
        slot(1, Fraction(0), _Q, "2"),
        *[slot(1, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert tie_layout(score=after) == []
    assert list(before_tied.relations) == []
    assert list(after_tied.relations) == []
    assert anchor_layout(score=after) == [
        (measure, Fraction(beat, 4)) for measure in range(2) for beat in range(4)
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_removing_the_measure_a_triplet_crosses_into_keeps_its_first_part() -> None:
    """Removing measure two splits the crossing triplet at the barline and drops its inner part.

    The part left in measure one keeps the same ratio over a quarter; the tie into the
    removed measure goes.
    """
    score: Score = crossing_triplet()

    apply_intent(score=score, intent=remove_measure(measure=score.measures[1]))

    after: Score = refresh_score(score=score)
    assert after.measures == [score.measures[0]]
    assert group_spans(score=after) == [(0, Fraction(3, 4), Fraction(3, 8), _Q, 0)]
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        slot(0, Fraction(3, 4), _Q, "1", depth=1),
        slot(0, Fraction(11, 12), _E, "2", depth=1),
    ]
    assert tie_layout(score=after) == []
    assert anchor_layout(score=after) == [
        *[(0, Fraction(beat, 4)) for beat in range(4)],
        (0, Fraction(11, 12)),
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_removing_the_measure_a_tuplet_starts_in_keeps_its_part_in_the_next() -> None:
    """Removing measure one keeps the sextuplet's part after the barline, now opening the score."""
    score: Score = _sextuplet_across_the_barline()

    apply_intent(score=score, intent=remove_measure(measure=score.measures[0]))

    after: Score = refresh_score(score=score)
    assert after.measures == [score.measures[1]]
    assert group_spans(score=after) == [(0, Fraction(0), Fraction(3, 8), _Q, 0)]
    assert layout(score=after) == [
        *[slot(0, index * _SIXTH, _E, str(4 + index), depth=1) for index in range(3)],
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert tie_layout(score=after) == []
    assert anchor_layout(score=after) == [
        (0, Fraction(0)),
        (0, _SIXTH),
        (0, 2 * _SIXTH),
        *[(0, Fraction(beat, 4)) for beat in range(1, 4)],
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_removing_a_measure_a_tuplet_spans_whole_keeps_its_parts_on_both_sides() -> None:
    """A tuplet over the whole removed measure keeps its two outer parts.

    Four dotted halves in the time of two wholes run from beat three of measure one into
    measure three. Removing measure two splits the tuplet at both barlines and drops the
    part inside; each outer part keeps the ratio — a dotted half in the time of a half.
    """
    score: Score = build_score(measure_count=3)
    quarters(score=score, measure=0, beats=(0, 1))
    tuplet: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=_H,
        written=size(RhythmicValue.WHOLE, count=3),
        occupied=size(RhythmicValue.WHOLE, count=2),
    )
    for index in range(4):
        note(
            score=score,
            parent=tuplet,
            at=_H + index * _H,
            rhythmic_value=RhythmicValue.HALF,
            dots=1,
            step=index + 1,
        )
    quarters(score=score, measure=2, beats=(2, 3))

    apply_intent(score=score, intent=remove_measure(measure=score.measures[1]))

    after: Score = refresh_score(score=score)
    assert after.measures == [score.measures[0], score.measures[2]]
    assert group_spans(score=after) == [
        (0, _H, Fraction(3, 4), _H, 0),
        (1, Fraction(0), Fraction(3, 4), _H, 0),
    ]
    assert layout(score=after) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "0"),
        slot(0, _H, Fraction(3, 4), "1", depth=1),
        slot(1, Fraction(0), Fraction(3, 4), "4", depth=1),
        slot(1, _H, _Q, "0"),
        slot(1, Fraction(3, 4), _Q, "0"),
    ]
    assert tie_layout(score=after) == []
    assert anchor_layout(score=after) == [
        (0, Fraction(0)),
        (0, _Q),
        (0, _H),
        (1, Fraction(0)),
        (1, _H),
        (1, Fraction(3, 4)),
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_removing_a_measure_repairs_the_contexts_that_reach_into_it() -> None:
    """Removing measure two repairs every context that reaches into it.

    The clef on its beat two and the start of the slur into measure three move right to the
    start of what was measure three; the end of the hairpin from measure one moves left to
    that same boundary; the slur starting and ending inside it is removed. The clef in
    measure three stays.
    """
    score: Score = build_score(measure_count=3)
    for measure in range(3):
        quarters(score=score, measure=measure)
    moved_clef: ClefChange = ClefChange.create(
        start=anchor_at(score=score, at=1 + _Q),
        staff=score.staff,
        clef=Clef.BASS,
    )
    kept_clef: ClefChange = ClefChange.create(
        start=anchor_at(score=score, at=2 + _H),
        staff=score.staff,
        clef=Clef.TREBLE,
    )
    hairpin: Hairpin = Hairpin.create(
        start=anchor_at(score=score, at=_Q),
        end=anchor_at(score=score, at=1 + _H),
        voice=score.voice,
        steps=1,
    )
    Slur.create(
        start=anchor_at(score=score, at=Fraction(1)),
        end=anchor_at(score=score, at=Fraction(7, 4)),
        voice=score.voice,
    )
    out_of: Slur = Slur.create(
        start=anchor_at(score=score, at=1 + _Q),
        end=anchor_at(score=score, at=2 + _H),
        voice=score.voice,
    )

    apply_intent(score=score, intent=remove_measure(measure=score.measures[1]))

    after: Score = refresh_score(score=score)
    assert after.measures == [score.measures[0], score.measures[2]]
    assert context_layout(score=after) == [
        ("Hairpin", (0, _Q), (1, Fraction(0))),
        ("ClefChange", (1, Fraction(0)), None),
        ("Slur", (1, Fraction(0)), (1, _H)),
        ("ClefChange", (1, _H), None),
    ]
    assert own_contexts(score, score.staff.contexts) == [moved_clef, kept_clef]
    assert own_contexts(score, score.voice.contexts) == [hairpin, out_of]
    assert layout(score=after) == [
        slot(measure, Fraction(beat, 4), _Q, "0") for measure in range(2) for beat in range(4)
    ]
    assert tie_layout(score=after) == []
    assert anchor_layout(score=after) == [
        (measure, Fraction(beat, 4)) for measure in range(2) for beat in range(4)
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_removing_a_measure_keeps_a_dynamic_for_the_voice_that_still_has_it_in_force() -> None:
    first, second = build_two_voices(measure_count=3)
    for measure in range(3):
        quarters(score=first, measure=measure)
        quarters(score=second, measure=measure)
    on_first: DynamicChange = DynamicChange.create(
        start=anchor_at(score=first, at=_Q), voice=first.voice, dynamic=DynamicMarking.FORTE
    )
    on_second: DynamicChange = DynamicChange.create(
        start=anchor_at(score=first, at=_Q), voice=second.voice, dynamic=DynamicMarking.FORTE
    )
    later_on_first: DynamicChange = DynamicChange.create(
        start=anchor_at(score=first, at=Fraction(1)),
        voice=first.voice,
        dynamic=DynamicMarking.PIANO,
    )

    apply_intent(score=first, intent=remove_measure(measure=first.measures[0]))

    # the first voice has another dynamic where the measure ends: the one in the measure goes;
    # the second voice has none there: its dynamic stays, at the start of what is left
    assert on_first not in first.voice.contexts
    assert on_second in second.voice.contexts
    assert on_second.start.measure is first.measures[1]
    assert on_second.start.position == MEASURE_START
    assert later_on_first in first.voice.contexts


@pytest.mark.unit
@_PENDING
def test_removing_the_first_measure_moves_what_the_score_starts_with_to_the_new_first_one() -> None:
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1)
    started_with: list[Context] = [
        *score.staff.contexts,
        *score.voice.contexts,
        *score.measures[0].anchors[0].starting_contexts,
    ]

    apply_intent(score=score, intent=remove_measure(measure=score.measures[0]))

    after: Score = refresh_score(score=score)
    assert after.measures == [score.measures[1]]
    assert score.document.missing_initial_contexts() == []
    assert all(context.start.measure is score.measures[1] for context in started_with)
    assert all(context.start.position == MEASURE_START for context in started_with)
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_removing_the_last_remaining_measure_is_refused_and_changes_nothing() -> None:
    """Its contexts too: clearing them out of the measure is undone with the refusal."""
    score: Score = four_quarters()
    clef: ClefChange = ClefChange.create(
        start=anchor_at(score=score, at=_Q),
        staff=score.staff,
        clef=Clef.BASS,
    )
    slur: Slur = Slur.create(
        start=anchor_at(score=score, at=Fraction(0)),
        end=anchor_at(score=score, at=_H),
        voice=score.voice,
    )
    before: Snapshot = snapshot(score=score)
    contexts_before: list[ContextSlot] = context_layout(score=score)

    with pytest.raises(MutationRejectedError, match=_LAST_MEASURE):
        apply_intent(score=score, intent=remove_measure(measure=score.measures[0]))

    assert list(score.document.measures) == score.measures
    assert snapshot(score=score) == before
    assert context_layout(score=score) == contexts_before
    assert (
        own_contexts(score, score.staff.contexts),
        own_contexts(score, score.voice.contexts),
    ) == ([clef], [slur])


@pytest.mark.unit
@_PENDING
def test_inserting_at_the_barline_of_nested_tuplets_splits_each_level() -> None:
    """A tuplet crossing the barline inside a tuplet crossing it is split the same way.

    Three halves in the time of a whole run [1/2, 3/2); inside them three quarters in the
    time of a half run [5/6, 7/6) with q e | e q, cut at the barline. Each level is split at
    the barline with its ratio, and the inner second part moves into the outer second part.
    """
    score: Score = build_score(measure_count=2)
    _nested_tuplets_across(score=score, barline=1)
    quarters(score=score, measure=1, beats=(2, 3))

    apply_intent(score=score, intent=insert_measure(before=score.measures[1]))

    after: Score = refresh_score(score=score)
    assert group_spans(score=after) == [
        (0, _H, Fraction(3, 4), _H, 0),
        (0, Fraction(5, 6), Fraction(3, 8), _Q, 1),
        (2, Fraction(0), Fraction(3, 4), _H, 0),
        (2, Fraction(0), Fraction(3, 8), _Q, 1),
    ]
    assert layout(score=after) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "0"),
        slot(0, _H, _H, "1", depth=1),
        slot(0, Fraction(5, 6), _Q, "2", depth=2),
        slot(0, Fraction(17, 18), _E, "3", depth=2),
        slot(2, Fraction(0), _E, "4", depth=2),
        slot(2, Fraction(1, 18), _Q, "5", depth=2),
        slot(2, Fraction(1, 6), _H, "6", depth=1),
        slot(2, _H, _Q, "0"),
        slot(2, Fraction(3, 4), _Q, "0"),
    ]
    assert list(after.measures[1].anchors) == []
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_removing_the_last_measure_removes_its_clef_and_opens_the_slur_ending_in_it() -> None:
    """With nothing to its right, a clef change at the end of the score is not pulled back.

    The slur from beat two of measure one ending in measure two now lasts until the end of the
    score, which is what is left of it; the slur inside measure one stays.
    """
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1)
    ClefChange.create(start=anchor_at(score=score, at=1 + _H), staff=score.staff, clef=Clef.BASS)
    Slur.create(
        start=anchor_at(score=score, at=_Q),
        end=anchor_at(score=score, at=1 + _Q),
        voice=score.voice,
    )
    kept: Slur = Slur.create(
        start=anchor_at(score=score, at=Fraction(0)),
        end=anchor_at(score=score, at=_H),
        voice=score.voice,
    )

    apply_intent(score=score, intent=remove_measure(measure=score.measures[1]))

    after: Score = refresh_score(score=score)
    assert after.measures == [score.measures[0]]
    assert context_layout(score=after) == [
        ("Slur", (0, Fraction(0)), (0, _H)),
        ("Slur", (0, _Q), (1, Fraction(0))),
    ]
    assert own_contexts(score, score.staff.contexts) == []
    assert kept in own_contexts(score, score.voice.contexts)
    assert len(own_contexts(score, score.voice.contexts)) == 2
    assert layout(score=after) == [slot(0, Fraction(beat, 4), _Q, "0") for beat in range(4)]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_a_span_context_whose_whole_time_lies_in_the_removed_measure_is_removed() -> None:
    """A hairpin from beat two of measure two to the next barline lies wholly in measure two.

    Moving its start to the boundary would leave it nothing, so it goes with the measure.
    """
    score: Score = build_score(measure_count=3)
    for measure in range(3):
        quarters(score=score, measure=measure)
    Hairpin.create(
        start=anchor_at(score=score, at=1 + _Q),
        end=anchor_at(score=score, at=Fraction(2)),
        voice=score.voice,
        steps=1,
    )

    apply_intent(score=score, intent=remove_measure(measure=score.measures[1]))

    after: Score = refresh_score(score=score)
    assert context_layout(score=after) == []
    assert own_contexts(score, score.voice.contexts) == []
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_undo_and_redo_of_an_insert_that_splits_a_tuplet_restore_each_side() -> None:
    score: Score = _sextuplet_across_the_barline()
    before: Snapshot = snapshot(score=score)

    log: MutationLog = apply_intent(score=score, intent=insert_measure(before=score.measures[1]))
    after: Score = refresh_score(score=score)
    inserted: Snapshot = snapshot(score=after)

    log.rollback()
    assert list(score.document.measures) == score.measures
    assert [measure.prev_measure for measure in score.measures] == [None, score.measures[0]]
    assert snapshot(score=score) == before

    log.reapply()
    assert list(score.document.measures) == after.measures
    assert snapshot(score=after) == inserted
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_undo_and_redo_of_a_removal_restore_each_side_with_its_contexts() -> None:
    """Undo brings back the measure, its elements, the split tuplet and the moved slur start.

    Removing measure one moves the slur's start right to the start of measure two.
    """
    score: Score = _sextuplet_across_the_barline()
    slur: Slur = Slur.create(
        start=anchor_at(score=score, at=_Q),
        end=anchor_at(score=score, at=1 + _H),
        voice=score.voice,
    )
    before: Snapshot = snapshot(score=score)
    contexts_before: list[ContextSlot] = context_layout(score=score)

    log: MutationLog = apply_intent(score=score, intent=remove_measure(measure=score.measures[0]))
    after: Score = refresh_score(score=score)
    removed: Snapshot = snapshot(score=after)
    contexts_removed: list[ContextSlot] = context_layout(score=after)
    assert contexts_removed == [("Slur", (0, Fraction(0)), (0, _H))]

    log.rollback()
    assert list(score.document.measures) == score.measures
    assert snapshot(score=score) == before
    assert context_layout(score=score) == contexts_before
    assert slur.start.measure is score.measures[0]

    log.reapply()
    assert list(score.document.measures) == after.measures
    assert snapshot(score=after) == removed
    assert context_layout(score=after) == contexts_removed


@pytest.mark.unit
@_PENDING
def test_removing_a_middle_measure_splits_nested_tuplets_at_its_end_barline() -> None:
    """Nested tuplets crossing out of the removed measure keep their parts after it.

    Both levels are split at the barline after measure two; the parts inside it go with it,
    the second parts now open measure two.
    """
    score: Score = build_score(measure_count=3)
    quarters(score=score, measure=0)
    _nested_tuplets_across(score=score, barline=2)
    quarters(score=score, measure=2, beats=(2, 3))

    apply_intent(score=score, intent=remove_measure(measure=score.measures[1]))

    after: Score = refresh_score(score=score)
    assert after.measures == [score.measures[0], score.measures[2]]
    assert group_spans(score=after) == [
        (1, Fraction(0), Fraction(3, 4), _H, 0),
        (1, Fraction(0), Fraction(3, 8), _Q, 1),
    ]
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(4)],
        slot(1, Fraction(0), _E, "4", depth=2),
        slot(1, Fraction(1, 18), _Q, "5", depth=2),
        slot(1, Fraction(1, 6), _H, "6", depth=1),
        slot(1, _H, _Q, "0"),
        slot(1, Fraction(3, 4), _Q, "0"),
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_an_insert_splits_a_tuplet_of_a_second_voice_and_leaves_the_first_alone() -> None:
    first, second = build_two_voices(measure_count=2)
    numbered_quarters(score=first, measure=0, first_step=1)
    numbered_quarters(score=first, measure=1, first_step=5)
    _add_sextuplet_across_the_barline(score=second)

    apply_intent(score=first, intent=insert_measure(before=first.measures[1]))

    after_first: Score = refresh_score(score=first)
    after_second: Score = refresh_score(score=second)
    assert group_spans(score=after_first) == []
    assert layout(score=after_first) == [
        *[slot(0, Fraction(beat, 4), _Q, str(1 + beat)) for beat in range(4)],
        *[slot(2, Fraction(beat, 4), _Q, str(5 + beat)) for beat in range(4)],
    ]
    assert group_spans(score=after_second) == [
        (0, Fraction(3, 4), Fraction(3, 8), _Q, 0),
        (2, Fraction(0), Fraction(3, 8), _Q, 0),
    ]
    assert layout(score=after_second) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        *[
            slot(0, Fraction(3, 4) + index * _SIXTH, _E, str(1 + index), depth=1)
            for index in range(3)
        ],
        *[slot(2, index * _SIXTH, _E, str(4 + index), depth=1) for index in range(3)],
        *[slot(2, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert list(after_first.measures[1].anchors) == []
    assert orphan_anchors(score=after_first) == []


@pytest.mark.unit
@_PENDING
def test_undo_and_redo_of_a_nested_split_restore_every_list_by_identity() -> None:
    """Undo puts every container back under its old parent, in its old place, and every
    anchor lists its containers as before; redo brings back the very same split groups."""
    score: Score = build_score(measure_count=2)
    _nested_tuplets_across(score=score, barline=1)
    quarters(score=score, measure=1, beats=(2, 3))

    def lists() -> list[list[object]]:
        containers: list[list[object]] = [
            list(anchor.containers)
            for measure in score.document.measures
            for anchor in measure.anchors
        ]
        children: list[list[object]] = [[*score.voice.children]]
        pending: list[RhythmicContainer] = list(score.voice.children)
        while pending:
            container: RhythmicContainer = pending.pop()
            if isinstance(container, GroupRhythmicContainer):
                children.append([container, container.written_size, *container.children])
                pending.extend(container.children)

        return [list(score.document.measures), *containers, *children]

    before: list[list[object]] = lists()

    log: MutationLog = apply_intent(score=score, intent=insert_measure(before=score.measures[1]))
    after: list[list[object]] = lists()

    log.rollback()
    assert lists() == before

    log.reapply()
    assert lists() == after


def _piano_of_quarters(*, measure_count: int) -> tuple[Piano, Score]:
    """One voice over two staffs, quarters on the upper staff in every measure; the score
    view is on the upper staff."""
    piano: Piano = build_piano(measure_count=measure_count)
    score: Score = Score(
        document=piano.document,
        voice=piano.voice,
        staff=piano.upper,
        measures=piano.measures,
        start_context_ids=piano.start_context_ids,
    )
    for measure in range(measure_count):
        quarters(score=score, measure=measure)

    return piano, score


@pytest.mark.unit
@_PENDING
def test_a_clef_whose_region_ends_at_the_next_clef_of_its_staff_goes_with_the_measure() -> None:
    """The bass clef on beat two of measure two governs only until the treble clef starting
    measure three; nothing of its region remains, and the clef already there is kept."""
    piano, score = _piano_of_quarters(measure_count=3)
    ClefChange.create(start=anchor_at(score=score, at=1 + _Q), staff=piano.upper, clef=Clef.BASS)
    kept: ClefChange = ClefChange.create(
        start=anchor_at(score=score, at=Fraction(2)),
        staff=piano.upper,
        clef=Clef.TREBLE,
    )

    apply_intent(score=score, intent=remove_measure(measure=score.measures[1]))

    after: Score = refresh_score(score=score)
    assert context_layout(score=after) == [("ClefChange", (1, Fraction(0)), None)]
    assert own_contexts(piano, piano.upper.contexts) == [kept]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_a_clef_on_the_other_staff_does_not_block_the_move() -> None:
    """The lower staff's clef starting measure three does not end the upper staff's clef
    region, so the upper clef moves to the start of measure three beside it."""
    piano, score = _piano_of_quarters(measure_count=3)
    moved: ClefChange = ClefChange.create(
        start=anchor_at(score=score, at=1 + _Q),
        staff=piano.upper,
        clef=Clef.BASS,
    )
    other: ClefChange = ClefChange.create(
        start=anchor_at(score=score, at=Fraction(2)),
        staff=piano.lower,
        clef=Clef.BASS,
    )

    apply_intent(score=score, intent=remove_measure(measure=score.measures[1]))

    after: Score = refresh_score(score=score)
    assert moved.start is other.start
    assert moved.start.measure is score.measures[2]
    assert moved.start.position == MeasurePosition.of_fraction(fraction=Fraction(0))
    assert (
        own_contexts(piano, piano.upper.contexts),
        own_contexts(piano, piano.lower.contexts),
    ) == ([moved], [other])
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
@pytest.mark.parametrize("blocked", [False, True], ids=["moved", "blocked"])
def test_a_key_signature_follows_the_same_region_rule(blocked: bool) -> None:
    """A key signature in the removed measure moves to the next measure's start, unless a key
    signature of its staff already starts there — then it goes and that one is kept."""
    piano, score = _piano_of_quarters(measure_count=3)
    moved: KeySignatureChange = KeySignatureChange.create(
        start=anchor_at(score=score, at=1 + _H),
        staff=piano.upper,
    )
    kept: list[KeySignatureChange] = (
        [KeySignatureChange.create(start=anchor_at(score=score, at=Fraction(2)), staff=piano.upper)]
        if blocked
        else []
    )

    apply_intent(score=score, intent=remove_measure(measure=score.measures[1]))

    after: Score = refresh_score(score=score)
    assert own_contexts(piano, piano.upper.contexts) == (kept if blocked else [moved])
    assert context_layout(score=after) == [("KeySignatureChange", (1, Fraction(0)), None)]
    assert orphan_anchors(score=after) == []


def _beam_across_the_barline() -> tuple[Score, Beam]:
    """Build quarters on beats one to three of measure one, eighths (steps 1, 2) on beat four,
    eighths (steps 3, 4) on beat one of measure two and quarters after; the four eighths are
    beamed across the barline."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(0, 1, 2))
    for index, at in enumerate((Fraction(3, 4), Fraction(7, 8), Fraction(1), Fraction(9, 8))):
        note(
            score=score,
            parent=score.voice,
            at=at,
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index + 1,
        )
    quarters(score=score, measure=1, beats=(1, 2, 3))
    carriers: list[Carrier] = [
        note_at(score=score, at=at).note_carrier
        for at in (Fraction(3, 4), Fraction(7, 8), Fraction(1), Fraction(9, 8))
    ]

    return score, Beam.create(carriers=carriers)


@pytest.mark.unit
@_PENDING
@pytest.mark.parametrize(
    ("removed", "kept"), [(0, slice(2, 4)), (1, slice(0, 2))], ids=["head", "tail"]
)
def test_removing_either_side_of_a_beam_across_the_barline_keeps_the_other_side_beamed(
    removed: int,
    kept: slice,
) -> None:
    """Whichever measure goes, the beam stays on the two eighths left — however the removed
    measure's anchors are ordered."""
    score, beam = _beam_across_the_barline()
    members: list[Carrier] = list(beam.members)

    apply_intent(score=score, intent=remove_measure(measure=score.measures[removed]))

    assert list(beam.members) == members[kept]
    assert all(list(carrier.carrier_group_relations) == [beam] for carrier in members[kept])
    assert orphan_anchors(score=refresh_score(score=score)) == []


@pytest.mark.unit
@_PENDING
def test_a_measure_inserted_inside_a_beam_cuts_it_into_the_runs_on_either_side() -> None:
    """The beam keeps the two eighths before the new measure; the two after it get a beam of
    their own."""
    score, beam = _beam_across_the_barline()
    members: list[Carrier] = list(beam.members)

    apply_intent(score=score, intent=insert_measure(before=score.measures[1]))

    assert list(beam.members) == members[:2]
    assert all(list(carrier.carrier_group_relations) == [beam] for carrier in members[:2])
    assert [list(found.members) for found in find_beams(carriers=members[2:])] == [members[2:]]
    assert orphan_anchors(score=refresh_score(score=score)) == []


@pytest.mark.unit
@_PENDING
def test_removing_a_measure_in_the_middle_of_a_beam_closes_it_up() -> None:
    """Eighths (steps 1, 2) end measure one, a 2/8 measure holds two more (steps 3, 4) and
    eighths (steps 5, 6) open measure three, all on one beam. Removing the middle measure
    takes its two out of the beam; the eighths on either side now touch and stay on it."""
    score: Score = build_score_with(
        time_signatures=[_FOUR_FOUR, size(RhythmicValue.EIGHTH, count=2), _FOUR_FOUR]
    )
    quarters(score=score, measure=0, beats=(0, 1, 2))
    places: list[Fraction] = [
        Fraction(3, 4),
        Fraction(7, 8),
        Fraction(1),
        Fraction(9, 8),
        Fraction(2),
        Fraction(17, 8),
    ]
    members: list[Carrier] = []
    for index, at in enumerate(places):
        carrier: Carrier | None = note(
            score=score,
            parent=score.voice,
            at=at,
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index + 1,
        ).carrier
        assert carrier is not None
        members.append(carrier)
    quarters(score=score, measure=2, beats=(1, 2, 3))
    beam: Beam = Beam.create(carriers=members)

    apply_intent(score=score, intent=remove_measure(measure=score.measures[1]))

    kept: list[Carrier] = [*members[:2], *members[4:]]
    assert list(beam.members) == kept
    assert all(list(carrier.carrier_group_relations) == [beam] for carrier in kept)
    assert orphan_anchors(score=refresh_score(score=score)) == []


def _crossing_contexts() -> tuple[Score, ClefChange, Slur]:
    """Build four measures of quarters, a bass clef on beat two of measure two and a slur from
    beat two of measure one to beat three of measure three."""
    score: Score = build_score(measure_count=4)
    for measure in range(4):
        quarters(score=score, measure=measure)
    clef: ClefChange = ClefChange.create(
        start=anchor_at(score=score, at=1 + _Q),
        staff=score.staff,
        clef=Clef.BASS,
    )
    slur: Slur = Slur.create(
        start=anchor_at(score=score, at=_Q),
        end=anchor_at(score=score, at=2 + _H),
        voice=score.voice,
    )

    return score, clef, slur


@pytest.mark.unit
@_PENDING
@pytest.mark.parametrize("in_one_batch", [True, False], ids=["batch", "in-sequence"])
def test_removing_two_adjacent_measures_carries_the_crossing_contexts_through_both(
    in_one_batch: bool,
) -> None:
    """Measures two and three go, in one batch or one after the other.

    The clef moves to the start of measure three, then on to the start of measure four; the
    slur's end in measure three moves left to the same boundary. Both end on the first beat
    of what was measure four.
    """
    score, clef, slur = _crossing_contexts()
    second, third = score.measures[1], score.measures[2]

    if in_one_batch:
        apply_intent(score=score, intent=DeleteBatchIntent(entity_ids=(second.id, third.id)))
    else:
        apply_intent(score=score, intent=remove_measure(measure=second))
        apply_intent(score=score, intent=remove_measure(measure=third))

    after: Score = refresh_score(score=score)
    assert after.measures == [score.measures[0], score.measures[3]]
    assert context_layout(score=after) == [
        ("Slur", (0, _Q), (1, Fraction(0))),
        ("ClefChange", (1, Fraction(0)), None),
    ]
    assert (
        own_contexts(score, score.staff.contexts),
        own_contexts(score, score.voice.contexts),
    ) == ([clef], [slur])
    assert layout(score=after) == [
        slot(measure, Fraction(beat, 4), _Q, "0") for measure in range(2) for beat in range(4)
    ]
    assert orphan_anchors(score=after) == []
