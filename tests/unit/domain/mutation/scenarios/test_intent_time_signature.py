from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.context import ClefChange, Hairpin, Slur
from piano_app.domain.score.document.models.material import Carrier, Note, NoteCarrier
from piano_app.domain.score.document.models.notation import (
    Accidental,
    Clef,
    GlissandoType,
    RhythmicSize,
    RhythmicValue,
)
from piano_app.domain.score.document.models.relations import Beam, Glissando, Tie
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    TemporalAnchor,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
)
from piano_app.domain.score.document.services.helpers import iter_leaves
from piano_app.domain.score.document.services.mutation.compiler import (
    EditIntent,
    TieNotesIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateClefChangeRequest,
)

from ...scene import (
    ContextSlot,
    Score,
    Slot,
    Snapshot,
    TieSlot,
    anchor_at,
    anchor_layout,
    apply_intent,
    broken_relations,
    build_engine,
    build_score,
    build_score_with,
    build_two_voices,
    context_layout,
    crossing_triplet,
    eighth_triplet,
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
    rest,
    signatures,
    size,
    slot,
    snapshot,
    tie_layout,
)

# ChangeTimeSignature (time-signature-change): exactly the selected measures get the new
# signature. Inside the selection elements keep their position relative to its start and only
# the barlines move — whatever crosses a new barline is cut (notes tied, rests plain); tuplets
# stay whole. The number of measures follows the selection's total length, not its content
# (owner, 2026-10-20): it becomes ceil(total / new length) measures — added when it does not
# divide (the last completed by fill), removed from its end when fewer are needed — and no
# measure is removed just because it is empty. Measures before and after the selection keep
# their signature, and elements after it keep their measure and beat. A tuplet crossing the
# selection's end is split in two there (same ratio) only when the selection's length changes;
# its start never moves and is never split. A relation whose members are no longer neighbours
# — free room or a cut's extra pieces now lie between them — is broken by the relation guard
# after the rebar and after each cut.
#
# A scene position reads "measure index + position inside the measure"; ``note_at`` reads
# the timeline from the score's start.

_Q: Fraction = Fraction(1, 4)
_H: Fraction = Fraction(1, 2)
_E: Fraction = Fraction(1, 8)
_SIXTH: Fraction = Fraction(1, 12)  # one quarter-triplet eighth on the timeline
_TWO_FOUR: RhythmicSize = size(RhythmicValue.QUARTER, count=2)
_THREE_FOUR: RhythmicSize = size(RhythmicValue.QUARTER, count=3)
_FOUR_FOUR: RhythmicSize = size(RhythmicValue.QUARTER, count=4)

_PENDING = pending(stage=6)


def change_time_signature(*, measures: list[Measure], time_signature: RhythmicSize) -> EditIntent:
    """``ChangeTimeSignatureIntent(measure_ids, time_signature)`` over the selected measures."""
    return planned_intent(
        "ChangeTimeSignatureIntent",
        measure_ids=tuple(measure.id for measure in measures),
        time_signature=time_signature,
    )


def _two_numbered_measures_and_quarters() -> Score:
    """Build two measures of quarters on steps 1-8, then a measure of quarters on step 0."""
    score: Score = build_score(measure_count=3)
    numbered_quarters(score=score, measure=0, first_step=1)
    numbered_quarters(score=score, measure=1, first_step=5)
    quarters(score=score, measure=2)

    return score


@pytest.mark.unit
@_PENDING
def test_four_four_to_three_four_on_two_measures_adds_a_measure_and_keeps_what_follows() -> None:
    """Eight quarters keep their order from the selection's start over three 3/4 measures.

    The selected measures stay and a third is added, completed by fill. The measure after
    the selection keeps its signature, its content and its beats.
    """
    score: Score = _two_numbered_measures_and_quarters()

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:2], time_signature=_THREE_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert signatures(score=after) == [Fraction(3, 4)] * 3 + [Fraction(1)]
    assert after.measures[:2] == score.measures[:2]
    assert after.measures[3] is score.measures[2]
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, str(1 + beat)) for beat in range(3)],
        *[slot(1, Fraction(beat, 4), _Q, str(4 + beat)) for beat in range(3)],
        slot(2, Fraction(0), _Q, "7"),
        slot(2, _Q, _Q, "8"),
        slot(2, _H, _Q, "rest"),
        *[slot(3, Fraction(beat, 4), _Q, "0") for beat in range(4)],
    ]
    assert tie_layout(score=after) == []
    assert group_spans(score=after) == []
    assert anchor_layout(score=after) == [
        *[(measure, Fraction(beat, 4)) for measure in range(3) for beat in range(3)],
        *[(3, Fraction(beat, 4)) for beat in range(4)],
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_a_context_inside_the_selection_keeps_its_place_from_the_selection_start() -> None:
    """A clef an eighth after beat two of measure two moves with the content.

    It lies 9/8 after the selection's start, which in 3/4 measures is measure two at 3/8.
    """
    score: Score = _two_numbered_measures_and_quarters()
    build_engine().process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measures[1],
                position=MeasurePosition.of_fraction(fraction=_E),
                staff=score.staff,
                clef=Clef.BASS,
            )
        ],
    )

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:2], time_signature=_THREE_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert context_layout(score=after) == [("ClefChange", (1, Fraction(3, 8)), None)]
    assert anchor_layout(score=after) == [
        *[(0, Fraction(beat, 4)) for beat in range(3)],
        (1, Fraction(0)),
        (1, _Q),
        (1, Fraction(3, 8)),
        (1, _H),
        *[(2, Fraction(beat, 4)) for beat in range(3)],
        *[(3, Fraction(beat, 4)) for beat in range(4)],
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_three_four_to_four_four_on_four_measures_becomes_three_measures() -> None:
    """Four 3/4 measures (twelve quarters) last exactly three 4/4 measures.

    The fourth selected measure is removed; the 4/4 measure after stays as it was.
    """
    score: Score = build_score_with(time_signatures=[_THREE_FOUR] * 4 + [_FOUR_FOUR])
    for measure in range(4):
        numbered_quarters(score=score, measure=measure, first_step=1 + 3 * measure, count=3)
    quarters(score=score, measure=4)

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:4], time_signature=_FOUR_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert signatures(score=after) == [Fraction(1)] * 4
    assert after.measures == [*score.measures[:3], score.measures[4]]
    assert layout(score=after) == [
        *[
            slot(measure, Fraction(beat, 4), _Q, str(1 + 4 * measure + beat))
            for measure in range(3)
            for beat in range(4)
        ],
        *[slot(3, Fraction(beat, 4), _Q, "0") for beat in range(4)],
    ]
    assert tie_layout(score=after) == []
    assert anchor_layout(score=after) == [
        (measure, Fraction(beat, 4)) for measure in range(4) for beat in range(4)
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_a_selection_of_mixed_signatures_gets_the_new_one_and_its_neighbours_keep_theirs() -> None:
    """A selected 4/4 and 2/4 measure (steps 1-6) become two 3/4 measures.

    The 2/4 measure before and the 4/4 measure after keep their signatures and content.
    """
    score: Score = build_score_with(time_signatures=[_TWO_FOUR, _FOUR_FOUR, _TWO_FOUR, _FOUR_FOUR])
    quarters(score=score, measure=0, beats=(0, 1))
    numbered_quarters(score=score, measure=1, first_step=1)
    numbered_quarters(score=score, measure=2, first_step=5, count=2)
    quarters(score=score, measure=3)

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[1:3], time_signature=_THREE_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert signatures(score=after) == [_H, Fraction(3, 4), Fraction(3, 4), Fraction(1)]
    assert after.measures == score.measures
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(2)],
        *[slot(1, Fraction(beat, 4), _Q, str(1 + beat)) for beat in range(3)],
        *[slot(2, Fraction(beat, 4), _Q, str(4 + beat)) for beat in range(3)],
        *[slot(3, Fraction(beat, 4), _Q, "0") for beat in range(4)],
    ]
    assert tie_layout(score=after) == []
    assert anchor_layout(score=after) == [
        *[(0, Fraction(beat, 4)) for beat in range(2)],
        *[(measure, Fraction(beat, 4)) for measure in (1, 2) for beat in range(3)],
        *[(3, Fraction(beat, 4)) for beat in range(4)],
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_a_half_crossing_the_new_barline_is_cut_and_tied() -> None:
    """Two halves in a measure turned 3/4: the second is cut into two tied quarters.

    Fill completes the added measure.
    """
    score: Score = build_score(measure_count=2)
    note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.HALF,
        step=1,
    )
    note(score=score, parent=score.voice, at=_H, rhythmic_value=RhythmicValue.HALF, step=2)
    quarters(score=score, measure=1)

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:1], time_signature=_THREE_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert signatures(score=after) == [Fraction(3, 4), Fraction(3, 4), Fraction(1)]
    assert (after.measures[0], after.measures[2]) == (score.measures[0], score.measures[1])
    assert layout(score=after) == [
        slot(0, Fraction(0), _H, "1"),
        slot(0, _H, _Q, "2"),
        slot(1, Fraction(0), _Q, "2"),
        slot(1, _Q, _H, "rest"),
        *[slot(2, Fraction(beat, 4), _Q, "0") for beat in range(4)],
    ]
    assert tie_layout(score=after) == [TieSlot(start=(0, _H, 2), end=(1, Fraction(0), 2))]
    assert anchor_layout(score=after) == [
        (0, Fraction(0)),
        (0, _H),
        (1, Fraction(0)),
        (1, _Q),
        *[(2, Fraction(beat, 4)) for beat in range(4)],
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_a_rest_crossing_the_new_barline_is_cut_into_plain_rests() -> None:
    score: Score = build_score(measure_count=2)
    note(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.HALF,
        step=1,
    )
    rest(score=score, parent=score.voice, at=_H, rhythmic_value=RhythmicValue.HALF)
    quarters(score=score, measure=1)

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:1], time_signature=_THREE_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert signatures(score=after) == [Fraction(3, 4), Fraction(3, 4), Fraction(1)]
    assert layout(score=after) == [
        slot(0, Fraction(0), _H, "1"),
        slot(0, _H, _Q, "rest"),
        slot(1, Fraction(0), _Q, "rest"),
        slot(1, _Q, _H, "rest"),
        *[slot(2, Fraction(beat, 4), _Q, "0") for beat in range(4)],
    ]
    assert tie_layout(score=after) == []
    assert anchor_layout(score=after) == [
        (0, Fraction(0)),
        (0, _H),
        (1, Fraction(0)),
        (1, _Q),
        *[(2, Fraction(beat, 4)) for beat in range(4)],
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_a_tuplet_inside_the_selection_crossing_a_new_barline_stays_whole() -> None:
    """A quarter triplet on beats three and four of a measure turned 3/4 now crosses a barline.

    The triplet stays one group with the same sizes; its middle quarter is cut at the new
    barline into two tied eighths, and fill completes the added measure.
    """
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(0, 1))
    triplet: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=_H,
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
    )
    for index in range(3):
        note(
            score=score,
            parent=triplet,
            at=_H + index * 2 * _SIXTH,
            rhythmic_value=RhythmicValue.QUARTER,
            step=index + 1,
        )
    quarters(score=score, measure=1)

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:1], time_signature=_THREE_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert signatures(score=after) == [Fraction(3, 4), Fraction(3, 4), Fraction(1)]
    assert group_spans(score=after) == [(0, _H, Fraction(3, 4), _H, 0)]
    assert layout(score=after) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "0"),
        slot(0, _H, _Q, "1", depth=1),
        slot(0, Fraction(2, 3), _E, "2", depth=1),
        slot(1, Fraction(0), _E, "2", depth=1),
        slot(1, _SIXTH, _Q, "3", depth=1),
        slot(1, _Q, _H, "rest"),
        *[slot(2, Fraction(beat, 4), _Q, "0") for beat in range(4)],
    ]
    assert tie_layout(score=after) == [
        TieSlot(start=(0, Fraction(2, 3), 2), end=(1, Fraction(0), 2))
    ]
    assert anchor_layout(score=after) == [
        (0, Fraction(0)),
        (0, _Q),
        (0, _H),
        (0, Fraction(2, 3)),
        (1, Fraction(0)),
        (1, _SIXTH),
        (1, _Q),
        *[(2, Fraction(beat, 4)) for beat in range(4)],
    ]
    assert orphan_anchors(score=after) == []


def _tied_over_the_selection_end() -> Score:
    """Build three quarters and a quarter (step 1) tied over the barline to a quarter (step 1)."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(0, 1, 2))
    for at in (Fraction(3, 4), Fraction(1)):
        note(score=score, parent=score.voice, at=at, rhythmic_value=RhythmicValue.QUARTER, step=1)
    quarters(score=score, measure=1, beats=(1, 2, 3))
    apply_intent(
        score=score,
        intent=TieNotesIntent(
            start_note_id=note_at(score=score, at=Fraction(3, 4)).id,
            end_note_id=note_at(score=score, at=Fraction(1)).id,
        ),
    )

    return score


@pytest.mark.unit
@_PENDING
def test_a_tie_from_the_selection_that_no_longer_touches_the_next_note_is_removed() -> None:
    """In 3/4 the tied quarter moves to beat one of the added measure and the tie goes.

    It no longer touches the note it was tied to; fill completes the added measure.
    """
    score: Score = _tied_over_the_selection_end()

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:1], time_signature=_THREE_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert signatures(score=after) == [Fraction(3, 4), Fraction(3, 4), Fraction(1)]
    assert (after.measures[0], after.measures[2]) == (score.measures[0], score.measures[1])
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        slot(1, Fraction(0), _Q, "1"),
        slot(1, _Q, _H, "rest"),
        slot(2, Fraction(0), _Q, "1"),
        *[slot(2, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert tie_layout(score=after) == []
    assert anchor_layout(score=after) == [
        *[(0, Fraction(beat, 4)) for beat in range(3)],
        (1, Fraction(0)),
        (1, _Q),
        *[(2, Fraction(beat, 4)) for beat in range(4)],
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_a_tie_from_the_selection_that_still_touches_the_next_note_stays() -> None:
    """In 2/4 the tied quarter still touches the next note, so the tie stays.

    The four quarters fill two 2/4 measures exactly.
    """
    score: Score = _tied_over_the_selection_end()

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:1], time_signature=_TWO_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert signatures(score=after) == [_H, _H, Fraction(1)]
    assert (after.measures[0], after.measures[2]) == (score.measures[0], score.measures[1])
    assert layout(score=after) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "0"),
        slot(1, Fraction(0), _Q, "0"),
        slot(1, _Q, _Q, "1"),
        slot(2, Fraction(0), _Q, "1"),
        *[slot(2, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert tie_layout(score=after) == [TieSlot(start=(1, _Q, 1), end=(2, Fraction(0), 1))]
    assert anchor_layout(score=after) == [
        *[(measure, Fraction(beat, 4)) for measure in range(2) for beat in range(2)],
        *[(2, Fraction(beat, 4)) for beat in range(4)],
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_a_triplet_crossing_the_selection_end_stays_whole_when_the_length_divides() -> None:
    """In 2/4 the selection keeps its length, so its end does not move and the triplet over it
    stays one tuplet across the new barline.

    It moves with the selection to beat two of the added measure and reaches into the measure
    after; the middle quarter's pieces still touch and stay tied.
    """
    score: Score = crossing_triplet()

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:1], time_signature=_TWO_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert signatures(score=after) == [_H, _H, Fraction(1)]
    assert (after.measures[0], after.measures[2]) == (score.measures[0], score.measures[1])
    assert group_spans(score=after) == [(1, _Q, Fraction(3, 4), _H, 0)]
    assert layout(score=after) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "0"),
        slot(1, Fraction(0), _Q, "0"),
        slot(1, _Q, _Q, "1", depth=1),
        slot(1, Fraction(5, 12), _E, "2", depth=1),
        slot(2, Fraction(0), _E, "2", depth=1),
        slot(2, _SIXTH, _Q, "3", depth=1),
        *[slot(2, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert tie_layout(score=after) == [
        TieSlot(start=(1, Fraction(5, 12), 2), end=(2, Fraction(0), 2))
    ]
    assert anchor_layout(score=after) == [
        (0, Fraction(0)),
        (0, _Q),
        (1, Fraction(0)),
        (1, _Q),
        (1, Fraction(5, 12)),
        (2, Fraction(0)),
        (2, _SIXTH),
        *[(2, Fraction(beat, 4)) for beat in range(1, 4)],
    ]
    assert broken_relations(score=after) == []
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_a_triplet_split_at_the_selection_end_loses_a_tie_that_no_longer_touches() -> None:
    """In 3/4 the split triplet's parts no longer touch, so the tie between them goes.

    The first part opens the added measure and ends a half before the second part; fill
    completes the added measure after it.
    """
    score: Score = crossing_triplet()

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:1], time_signature=_THREE_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert signatures(score=after) == [Fraction(3, 4), Fraction(3, 4), Fraction(1)]
    assert group_spans(score=after) == [
        (1, Fraction(0), Fraction(3, 8), _Q, 0),
        (2, Fraction(0), Fraction(3, 8), _Q, 0),
    ]
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        slot(1, Fraction(0), _Q, "1", depth=1),
        slot(1, 2 * _SIXTH, _E, "2", depth=1),
        slot(1, _Q, _H, "rest"),
        slot(2, Fraction(0), _E, "2", depth=1),
        slot(2, _SIXTH, _Q, "3", depth=1),
        *[slot(2, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert tie_layout(score=after) == []
    assert anchor_layout(score=after) == [
        *[(0, Fraction(beat, 4)) for beat in range(3)],
        (1, Fraction(0)),
        (1, 2 * _SIXTH),
        (1, _Q),
        (2, Fraction(0)),
        (2, _SIXTH),
        *[(2, Fraction(beat, 4)) for beat in range(1, 4)],
    ]
    assert broken_relations(score=after) == []
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_a_triplet_crossing_the_selection_start_is_never_split() -> None:
    """In 2/4 on measure two only, the triplet over the selection's start stays one tuplet:
    the start never moves.

    It still opens in measure one and reaches into the selection; the middle quarter's
    pieces stay tied. The rest of measure two spills into an added 2/4 measure.
    """
    score: Score = crossing_triplet()

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[1:], time_signature=_TWO_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert signatures(score=after) == [Fraction(1), _H, _H]
    assert after.measures[:2] == score.measures
    assert group_spans(score=after) == [(0, Fraction(3, 4), Fraction(3, 4), _H, 0)]
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        slot(0, Fraction(3, 4), _Q, "1", depth=1),
        slot(0, Fraction(11, 12), _E, "2", depth=1),
        slot(1, Fraction(0), _E, "2", depth=1),
        slot(1, _SIXTH, _Q, "3", depth=1),
        slot(1, _Q, _Q, "0"),
        slot(2, Fraction(0), _Q, "0"),
        slot(2, _Q, _Q, "0"),
    ]
    assert tie_layout(score=after) == [
        TieSlot(start=(0, Fraction(11, 12), 2), end=(1, Fraction(0), 2))
    ]
    assert anchor_layout(score=after) == [
        *[(0, Fraction(beat, 4)) for beat in range(4)],
        (0, Fraction(11, 12)),
        (1, Fraction(0)),
        (1, _SIXTH),
        (1, _Q),
        (2, Fraction(0)),
        (2, _Q),
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_every_voice_of_the_selected_measures_is_placed_again() -> None:
    """Measures belong to every voice: in 3/4 both voices of the selected measure are re-placed.

    Voice one's fourth quarter moves to the added measure; voice two's whole note is cut at
    the new barline and tied. Fill completes the added measure in each voice.
    """
    first, second = build_two_voices(measure_count=2)
    numbered_quarters(score=first, measure=0, first_step=1)
    quarters(score=first, measure=1)
    for measure, step in ((0, 7), (1, 8)):
        note(
            score=second,
            parent=second.voice,
            at=Fraction(measure),
            rhythmic_value=RhythmicValue.WHOLE,
            step=step,
        )

    apply_intent(
        score=first,
        intent=change_time_signature(measures=first.measures[:1], time_signature=_THREE_FOUR),
    )

    first_after: Score = refresh_score(score=first)
    second_after: Score = refresh_score(score=second)
    assert signatures(score=first_after) == [Fraction(3, 4), Fraction(3, 4), Fraction(1)]
    assert layout(score=first_after) == [
        *[slot(0, Fraction(beat, 4), _Q, str(1 + beat)) for beat in range(3)],
        slot(1, Fraction(0), _Q, "4"),
        slot(1, _Q, _H, "rest"),
        *[slot(2, Fraction(beat, 4), _Q, "0") for beat in range(4)],
    ]
    assert layout(score=second_after) == [
        slot(0, Fraction(0), Fraction(3, 4), "7"),
        slot(1, Fraction(0), _Q, "7"),
        slot(1, _Q, _H, "rest"),
        slot(2, Fraction(0), Fraction(1), "8"),
    ]
    assert tie_layout(score=first_after) == []
    assert tie_layout(score=second_after) == [
        TieSlot(start=(0, Fraction(0), 7), end=(1, Fraction(0), 7))
    ]
    assert anchor_layout(score=first_after) == [
        *[(0, Fraction(beat, 4)) for beat in range(3)],
        (1, Fraction(0)),
        (1, _Q),
        *[(2, Fraction(beat, 4)) for beat in range(4)],
    ]
    assert orphan_anchors(score=first_after) == []


@pytest.mark.unit
@_PENDING
def test_the_elements_and_contexts_moved_by_the_change_keep_their_identity() -> None:
    """Nothing is taken off and placed again: the leaves, the contexts and the anchors are
    the same entities at their new places.

    A clef on 1/8 of measure two, a hairpin from beat two of measure one to beat four of
    measure two and a slur from beat three of measure two to beat three of measure three
    (after the selection): in 3/4 the clef lies at 3/8 of measure two, the hairpin runs to
    beat two of the added measure, the slur starts on its beat one and still ends on beat
    three of the measure after the selection.
    """
    score: Score = _two_numbered_measures_and_quarters()
    clef: ClefChange = ClefChange.create(
        start=anchor_at(score=score, at=1 + _E),
        staff=score.staff,
        clef=Clef.BASS,
    )
    hairpin: Hairpin = Hairpin.create(
        start=anchor_at(score=score, at=_Q),
        end=anchor_at(score=score, at=1 + 3 * _Q),
        voice=score.voice,
        steps=1,
    )
    slur: Slur = Slur.create(
        start=anchor_at(score=score, at=1 + _H),
        end=anchor_at(score=score, at=2 + _H),
        voice=score.voice,
    )
    leaves: list[LeafRhythmicContainer] = iter_leaves(score.voice)
    clef_anchor: TemporalAnchor = clef.start

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:2], time_signature=_THREE_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert context_layout(score=after) == [
        ("Hairpin", (0, _Q), (2, _Q)),
        ("ClefChange", (1, Fraction(3, 8)), None),
        ("Slur", (2, Fraction(0)), (3, _H)),
    ]
    assert clef.start is clef_anchor
    assert own_contexts(score, score.staff.contexts) == [clef]
    assert own_contexts(score, score.voice.contexts) == [hairpin, slur]
    # the eight numbered quarters, then the rest the fill added, then the measure after
    after_leaves: list[LeafRhythmicContainer] = iter_leaves(score.voice)
    assert after_leaves[:8] == leaves[:8]
    assert after_leaves[9:] == leaves[8:]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_a_tie_over_the_selection_end_stays_when_removed_measures_keep_it_touching() -> None:
    """Twelve quarters over four 3/4 measures become three 4/4 measures, the last tied over.

    The fourth selected measure is removed; the selection keeps its length, so the last
    quarter still touches the note after the selection and the tie stays.
    """
    score: Score = build_score_with(time_signatures=[_THREE_FOUR] * 4 + [_FOUR_FOUR])
    for measure in range(4):
        numbered_quarters(score=score, measure=measure, first_step=1 + 3 * measure, count=3)
    quarters(score=score, measure=4)
    # a tie joins notes of one pitch
    note_at(score=score, at=Fraction(3)).set_staff_step(staff_step=12)
    # ``note_at`` reads the timeline: the third quarter of measure four, beat one of measure five
    apply_intent(
        score=score,
        intent=TieNotesIntent(
            start_note_id=note_at(score=score, at=Fraction(11, 4)).id,
            end_note_id=note_at(score=score, at=Fraction(3)).id,
        ),
    )

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:4], time_signature=_FOUR_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert after.measures == [*score.measures[:3], score.measures[4]]
    assert tie_layout(score=after) == [TieSlot(start=(2, 3 * _Q, 12), end=(3, Fraction(0), 12))]
    assert orphan_anchors(score=after) == []


def _lists(*, score: Score) -> list[list[object]]:
    """Every list a change touches, by identity: the measures with their signatures, each
    measure's anchors, each anchor's containers and contexts, and every scope's children."""
    lists: list[list[object]] = [
        list(score.document.measures),
        [measure.time_signature for measure in score.document.measures],
    ]
    for measure in score.document.measures:
        lists.append(list(measure.anchors))
        for anchor in measure.anchors:
            lists.append(
                [
                    anchor.position,
                    *anchor.containers,
                    *anchor.starting_contexts,
                    *anchor.ending_contexts,
                ]
            )

    lists.append([*score.voice.children])
    lists.append([*score.voice.contexts])
    pending: list[RhythmicContainer] = list(score.voice.children)
    while pending:
        container: RhythmicContainer = pending.pop()
        if isinstance(container, GroupRhythmicContainer):
            lists.append([container, container.written_size, *container.children])
            pending.extend(container.children)

    return lists


@pytest.mark.unit
@_PENDING
def test_undo_and_redo_of_a_time_signature_change_restore_each_side_exactly() -> None:
    """3/4 on measure one of the crossing triplet: the triplet is split at the edge, its tie
    removed, a measure added and a slur from the selection to the measure after keeps both
    ends. Undo restores every list by identity, redo brings the very same change back."""
    score: Score = crossing_triplet()
    Slur.create(
        start=anchor_at(score=score, at=_Q),
        end=anchor_at(score=score, at=1 + _H),
        voice=score.voice,
    )
    before: Snapshot = snapshot(score=score)
    contexts_before: list[ContextSlot] = context_layout(score=score)
    lists_before: list[list[object]] = _lists(score=score)

    log: MutationLog = apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:1], time_signature=_THREE_FOUR),
    )
    after: Score = refresh_score(score=score)
    changed: Snapshot = snapshot(score=after)
    contexts_changed: list[ContextSlot] = context_layout(score=after)
    lists_changed: list[list[object]] = _lists(score=score)
    assert signatures(score=after) == [Fraction(3, 4), Fraction(3, 4), Fraction(1)]
    assert contexts_changed == [("Slur", (0, _Q), (2, _H))]

    log.rollback()
    assert list(score.document.measures) == score.measures
    assert snapshot(score=score) == before
    assert context_layout(score=score) == contexts_before
    assert _lists(score=score) == lists_before

    log.reapply()
    assert list(score.document.measures) == after.measures
    assert snapshot(score=after) == changed
    assert context_layout(score=after) == contexts_changed
    assert _lists(score=score) == lists_changed


@pytest.mark.unit
@_PENDING
def test_a_non_contiguous_selection_is_refused_and_changes_nothing() -> None:
    score: Score = build_score(measure_count=3)
    for measure in range(3):
        quarters(score=score, measure=measure)
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match="contiguous"):
        apply_intent(
            score=score,
            intent=change_time_signature(
                measures=[score.measures[0], score.measures[2]],
                time_signature=_THREE_FOUR,
            ),
        )

    assert list(score.document.measures) == score.measures
    assert signatures(score=score) == [Fraction(1)] * 3
    assert snapshot(score=score) == before


@pytest.mark.unit
@_PENDING
def test_a_selection_already_in_the_signature_is_left_as_it_is() -> None:
    """Same signature, nothing changes: the triplet over the selection's start is not
    split either."""
    score: Score = crossing_triplet()
    before: Snapshot = snapshot(score=score)

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[1:], time_signature=_FOUR_FOUR),
    )

    assert list(score.document.measures) == score.measures
    assert snapshot(score=score) == before


@pytest.mark.unit
@_PENDING
def test_twenty_empty_three_four_measures_turned_six_eight_stay_twenty() -> None:
    """Same length per measure, so the count is kept: nothing is removed for being empty."""
    score: Score = build_score_with(time_signatures=[_THREE_FOUR] * 20)
    six_eight: RhythmicSize = size(RhythmicValue.EIGHTH, count=6)

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures, time_signature=six_eight),
    )

    after: Score = refresh_score(score=score)
    assert after.measures == score.measures
    assert [measure.time_signature for measure in after.measures] == [six_eight] * 20
    assert layout(score=after) == []
    assert anchor_layout(score=after) == [(0, Fraction(0))]


@pytest.mark.unit
@_PENDING
def test_four_empty_four_four_measures_turned_three_four_become_six() -> None:
    """A whole note's worth four times is 16/3 measures of 3/4: six, the two added at the end.

    They stay asleep: the fill puts nothing in an empty voice.
    """
    score: Score = build_score(measure_count=4)

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures, time_signature=_THREE_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert after.measures[:4] == score.measures
    assert signatures(score=after) == [Fraction(3, 4)] * 6
    assert layout(score=after) == []
    assert anchor_layout(score=after) == [(0, Fraction(0))]


@pytest.mark.unit
@_PENDING
def test_an_empty_measure_at_the_selection_end_still_counts_toward_its_length() -> None:
    """A measure of quarters and an empty 4/4 measure become three 3/4 measures, not two.

    The selection lasts two whole notes, so the third measure is added although the content
    fits in two; the empty time after the content stays asleep, and the measure after the
    selection keeps its content.
    """
    score: Score = build_score(measure_count=3)
    numbered_quarters(score=score, measure=0, first_step=1)
    quarters(score=score, measure=2)

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:2], time_signature=_THREE_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert signatures(score=after) == [Fraction(3, 4)] * 3 + [Fraction(1)]
    assert after.measures[:2] == score.measures[:2]
    assert after.measures[3] is score.measures[2]
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, str(1 + beat)) for beat in range(3)],
        slot(1, Fraction(0), _Q, "4"),
        slot(1, _Q, _H, "rest"),
        *[slot(3, Fraction(beat, 4), _Q, "0") for beat in range(4)],
    ]
    assert orphan_anchors(score=after) == []


# --- relations over the selection's end: one rule for every relation ----------------------


def _beams(*, score: Score) -> list[list[tuple[int, Fraction]]]:
    """Every beam of the voice as the places (measure index, position) of its members."""
    beams: list[Beam] = []
    for leaf in iter_leaves(score.voice):
        carrier: Carrier | None = leaf.carrier
        if carrier is None:
            continue
        for relation in carrier.carrier_group_relations:
            if isinstance(relation, Beam) and not any(relation is beam for beam in beams):
                beams.append(relation)

    places: list[list[tuple[int, Fraction]]] = []
    for beam in beams:
        members: list[tuple[int, Fraction]] = []
        for member in beam.members:
            owner = member.owner
            assert isinstance(owner, LeafRhythmicContainer)
            members.append(
                (score.measures.index(owner.anchor.measure), owner.anchor.position.value)
            )
        places.append(members)

    return places


def _glissandi(*, score: Score) -> list[tuple[int, int]]:
    """Every glissando of the voice as (staff step of its start, staff step of its end)."""
    found: list[tuple[int, int]] = []
    for leaf in iter_leaves(score.voice):
        carrier: Carrier | None = leaf.carrier
        if not isinstance(carrier, NoteCarrier):
            continue
        for item in carrier.notes:
            for relation in item.relations:
                if isinstance(relation, Glissando) and relation.start is item:
                    found.append((relation.start.staff_step, relation.end.staff_step))

    return found


def _glissando_over_the_selection_end() -> Score:
    """Build three quarters and a quarter (step 1) gliding over the barline to a quarter
    (step 2), then three more quarters."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(0, 1, 2))
    note(
        score=score,
        parent=score.voice,
        at=Fraction(3, 4),
        rhythmic_value=RhythmicValue.QUARTER,
        step=1,
    )
    note(
        score=score,
        parent=score.voice,
        at=Fraction(1),
        rhythmic_value=RhythmicValue.QUARTER,
        step=2,
    )
    quarters(score=score, measure=1, beats=(1, 2, 3))
    Glissando.create(
        start_note=note_at(score=score, at=Fraction(3, 4)),
        end_note=note_at(score=score, at=Fraction(1)),
        glissando_type=GlissandoType.WAVY,
    )

    return score


@pytest.mark.unit
@_PENDING
@pytest.mark.parametrize(
    ("time_signature", "kept"),
    [(_TWO_FOUR, True), (_THREE_FOUR, False)],
    ids=["divides-exactly", "rests-added-between"],
)
def test_a_glissando_over_the_selection_end_stays_only_while_its_notes_are_neighbours(
    time_signature: RhythmicSize,
    kept: bool,
) -> None:
    """In 2/4 the four quarters fill two measures and the notes stay neighbours; in 3/4
    the rests completing the added measure lie between them, so the glissando goes."""
    score: Score = _glissando_over_the_selection_end()

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:1], time_signature=time_signature),
    )

    assert _glissandi(score=refresh_score(score=score)) == ([(1, 2)] if kept else [])


def _half_before_a_quarter(*, partner_step: int) -> Score:
    """Build two quarters and a half (step 1) on beat three, then a quarter on
    ``partner_step`` opening the next measure and three quarters."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(0, 1))
    note(score=score, parent=score.voice, at=_H, rhythmic_value=RhythmicValue.HALF, step=1)
    note(
        score=score,
        parent=score.voice,
        at=Fraction(1),
        rhythmic_value=RhythmicValue.QUARTER,
        step=partner_step,
    )
    quarters(score=score, measure=1, beats=(1, 2, 3))

    return score


def _cut_half_layout(*, partner_step: int) -> list[Slot]:
    """The two measures turned 3/4: the half cut into two quarters at the new barline."""
    return [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "0"),
        slot(0, _H, _Q, "1"),
        slot(1, Fraction(0), _Q, "1"),
        slot(1, _Q, _Q, str(partner_step)),
        slot(1, _H, _Q, "0"),
        slot(2, Fraction(0), _Q, "0"),
        slot(2, _Q, _Q, "0"),
        slot(2, _H, _Q, "rest"),
    ]


@pytest.mark.unit
@_PENDING
def test_a_cut_element_moves_its_glissando_to_the_last_piece() -> None:
    """Two measures turned 3/4: the half on beat three, with a glissando to the next note
    (step 2), crosses the new barline and is cut into two tied quarters.

    The cut moves the glissando to the last piece, the same object; that piece touches the
    partner, so the glissando stays.
    """
    score: Score = _half_before_a_quarter(partner_step=2)
    glissando: Glissando = Glissando.create(
        start_note=note_at(score=score, at=_H),
        end_note=note_at(score=score, at=Fraction(1)),
        glissando_type=GlissandoType.WAVY,
    )

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures, time_signature=_THREE_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert signatures(score=after) == [Fraction(3, 4)] * 3
    assert layout(score=after) == _cut_half_layout(partner_step=2)
    assert tie_layout(score=after) == [TieSlot(start=(0, _H, 1), end=(1, Fraction(0), 1))]
    assert _glissandi(score=after) == [(1, 2)]
    assert glissando.start is note_at(score=after, at=Fraction(3, 4))
    assert broken_relations(score=after) == []
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_a_cut_element_moves_its_tie_to_the_last_piece() -> None:
    """The same cut with a tie to the next note (step 1): the cut moves the tie, the same
    object, from the first piece to the last, which still touches, and ties the pieces."""
    score: Score = _half_before_a_quarter(partner_step=1)
    partner: Note = note_at(score=score, at=Fraction(1))
    tie: Tie = Tie.create(start_note=note_at(score=score, at=_H), end_note=partner)

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures, time_signature=_THREE_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert layout(score=after) == _cut_half_layout(partner_step=1)
    assert tie_layout(score=after) == [
        TieSlot(start=(0, _H, 1), end=(1, Fraction(0), 1)),
        TieSlot(start=(1, Fraction(0), 1), end=(1, _Q, 1)),
    ]
    assert note_at(score=after, at=Fraction(1)) is partner
    assert tie.start is note_at(score=after, at=Fraction(3, 4))
    assert broken_relations(score=after) == []
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_a_cut_chord_moves_the_tie_of_its_upper_note_to_the_last_piece() -> None:
    """The half on beat three is a chord (steps 1, 2) whose upper note is tied to the next
    note (step 2), which the cut does not meet: the tie, the same object, starts at the upper
    note of the last piece, and each note is tied across the new barline."""
    score: Score = _half_before_a_quarter(partner_step=2)
    chord: NoteCarrier = note_at(score=score, at=_H).note_carrier
    upper: Note = Note.create(
        note_carrier=chord,
        staff=score.staff,
        staff_step=2,
        accidental=Accidental.NATURAL,
    )
    partner: Note = note_at(score=score, at=Fraction(1))
    tie: Tie = Tie.create(start_note=upper, end_note=partner)

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures, time_signature=_THREE_FOUR),
    )

    after: Score = refresh_score(score=score)
    last_piece: NoteCarrier = note_at(score=after, at=Fraction(3, 4)).note_carrier
    assert [item.staff_step for item in last_piece.notes] == [1, 2]
    assert tie.start is last_piece.notes[1]
    assert tie.end is partner
    assert tie_layout(score=after) == [
        TieSlot(start=(0, _H, 1), end=(1, Fraction(0), 1)),
        TieSlot(start=(0, _H, 2), end=(1, Fraction(0), 2)),
        TieSlot(start=(1, Fraction(0), 2), end=(1, _Q, 2)),
    ]
    assert orphan_anchors(score=after) == []


def _beam_over_the_selection_end() -> Score:
    """Build three quarters, then four eighths (steps 1-4) beamed over the barline — two on
    each side — then three quarters."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(0, 1, 2))
    for index in range(4):
        note(
            score=score,
            parent=score.voice,
            at=Fraction(3, 4) + index * _E,
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index + 1,
        )
    quarters(score=score, measure=1, beats=(1, 2, 3))
    Beam.create(
        carriers=[
            note_at(score=score, at=Fraction(3, 4) + index * _E).note_carrier for index in range(4)
        ]
    )

    return score


@pytest.mark.unit
@_PENDING
def test_a_beam_over_the_selection_end_stays_whole_when_the_length_divides() -> None:
    score: Score = _beam_over_the_selection_end()

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:1], time_signature=_TWO_FOUR),
    )

    assert _beams(score=refresh_score(score=score)) == [
        [(1, _Q), (1, _Q + _E), (2, Fraction(0)), (2, _E)]
    ]


@pytest.mark.unit
@_PENDING
def test_a_beam_over_the_selection_end_is_cut_where_rests_now_lie_between() -> None:
    """In 3/4 the two eighths of the selection open the added measure and the rest after
    them separates them from the two after the selection: two beams of two."""
    score: Score = _beam_over_the_selection_end()
    beam: Beam = _first_beam(score=score)

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:1], time_signature=_THREE_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert _beams(score=after) == [
        [(1, Fraction(0)), (1, _E)],
        [(2, Fraction(0)), (2, _E)],
    ]
    assert broken_relations(score=after) == []
    assert _first_beam(score=after) is beam


@pytest.mark.unit
@_PENDING
def test_a_beam_over_a_new_barline_inside_the_selection_stays() -> None:
    """A barline is not an element between members: four eighths from beat three of a
    measure turned 3/4 now cross its barline and keep one beam."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(0, 1))
    for index in range(4):
        note(
            score=score,
            parent=score.voice,
            at=_H + index * _E,
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index + 1,
        )
    quarters(score=score, measure=1)
    Beam.create(
        carriers=[note_at(score=score, at=_H + index * _E).note_carrier for index in range(4)]
    )

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:1], time_signature=_THREE_FOUR),
    )

    assert _beams(score=refresh_score(score=score)) == [
        [(0, _H), (0, _H + _E), (1, Fraction(0)), (1, _E)]
    ]


def _first_beam(*, score: Score) -> Beam:
    for leaf in iter_leaves(score.voice):
        carrier: Carrier | None = leaf.carrier
        if carrier is None:
            continue
        for relation in carrier.carrier_group_relations:
            if isinstance(relation, Beam):
                return relation

    raise LookupError("The voice has no beam.")


# --- span contexts ending on the selection's end barline ----------------------------------


@pytest.mark.unit
@_PENDING
@pytest.mark.parametrize(
    ("time_signature", "end"),
    [(_THREE_FOUR, (1, _Q)), (_TWO_FOUR, (2, Fraction(0)))],
    ids=["padded", "divides-exactly"],
)
def test_a_hairpin_ending_on_the_selection_end_keeps_its_time_from_the_selection_start(
    time_signature: RhythmicSize,
    end: tuple[int, Fraction],
) -> None:
    """Its end stays a whole note after the selection's start: inside the added 3/4 measure,
    or on the same barline when 2/4 divides the selection exactly. The anchor opening the
    measure after the selection is not moved."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1)
    hairpin: Hairpin = Hairpin.create(
        start=anchor_at(score=score, at=_Q),
        end=anchor_at(score=score, at=Fraction(1)),
        voice=score.voice,
        steps=-1,
    )
    barline: TemporalAnchor = hairpin.end

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:1], time_signature=time_signature),
    )

    after: Score = refresh_score(score=score)
    assert context_layout(score=after) == [("Hairpin", (0, _Q), end)]
    assert (barline.measure, barline.position.value) == (score.measures[1], Fraction(0))
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
@pytest.mark.parametrize(
    ("time_signature", "end"),
    [(_THREE_FOUR, (2, _Q)), (_TWO_FOUR, (3, Fraction(0)))],
    ids=["padded", "divides-exactly"],
)
def test_a_slur_from_before_the_selection_ending_on_its_end_keeps_that_time(
    time_signature: RhythmicSize,
    end: tuple[int, Fraction],
) -> None:
    """A slur from beat three of measure one over the selected measure two to the barline
    after it: its end stays a whole note after the selection's start."""
    score: Score = build_score(measure_count=3)
    for measure in range(3):
        quarters(score=score, measure=measure)
    Slur.create(
        start=anchor_at(score=score, at=_H),
        end=anchor_at(score=score, at=Fraction(2)),
        voice=score.voice,
    )

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[1:2], time_signature=time_signature),
    )

    after: Score = refresh_score(score=score)
    assert context_layout(score=after) == [("Slur", (0, _H), end)]
    assert orphan_anchors(score=after) == []


# --- more selections ---------------------------------------------------------------------


@pytest.mark.unit
@_PENDING
def test_a_selection_at_the_end_of_the_score_appends_the_measure_it_needs() -> None:
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    numbered_quarters(score=score, measure=1, first_step=1)

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[1:], time_signature=_THREE_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert signatures(score=after) == [Fraction(1), Fraction(3, 4), Fraction(3, 4)]
    assert after.measures[:2] == score.measures
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(4)],
        *[slot(1, Fraction(beat, 4), _Q, str(1 + beat)) for beat in range(3)],
        slot(2, Fraction(0), _Q, "4"),
        slot(2, _Q, _H, "rest"),
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_a_tuplet_crossing_both_edges_of_the_selection_is_split_only_at_the_end() -> None:
    """Nine quarters in the time of six from beat four of measure one to beat two of measure
    three, cut and tied at both barlines; measure two turned 3/4.

    The selection grows, so its end moves and the tuplet splits there into two parts of the
    same ratio; its start never moves, so the first part stays whole from measure one across
    the new barline, its seventh quarter opening the added measure. The tie over the
    selection's start stays, the one over its end goes: rests now lie between its notes.
    """
    score: Score = build_score(measure_count=3)
    quarters(score=score, measure=0, beats=(0, 1, 2))
    tuplet: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=3 * _Q,
        written=size(RhythmicValue.QUARTER, count=9),
        occupied=size(RhythmicValue.QUARTER, count=6),
    )
    items: list[tuple[Fraction, RhythmicValue, int]] = [
        (3 * _Q, RhythmicValue.QUARTER, 1),
        (Fraction(11, 12), RhythmicValue.EIGHTH, 2),
        (Fraction(1), RhythmicValue.EIGHTH, 2),
        *[
            (Fraction(13, 12) + index * 2 * _SIXTH, RhythmicValue.QUARTER, 3 + index)
            for index in range(5)
        ],
        (Fraction(23, 12), RhythmicValue.EIGHTH, 8),
        (Fraction(2), RhythmicValue.EIGHTH, 8),
        (Fraction(25, 12), RhythmicValue.QUARTER, 9),
    ]
    for at, rhythmic_value, step in items:
        note(score=score, parent=tuplet, at=at, rhythmic_value=rhythmic_value, step=step)
    for start_at, end_at in ((Fraction(11, 12), Fraction(1)), (Fraction(23, 12), Fraction(2))):
        Tie.create(
            start_note=note_at(score=score, at=start_at),
            end_note=note_at(score=score, at=end_at),
        )
    quarters(score=score, measure=2, beats=(1, 2, 3))

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[1:2], time_signature=_THREE_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert signatures(score=after) == [Fraction(1), Fraction(3, 4), Fraction(3, 4), Fraction(1)]
    assert group_spans(score=after) == [
        (0, 3 * _Q, Fraction(15, 8), Fraction(5, 4), 0),
        (3, Fraction(0), Fraction(3, 8), _Q, 0),
    ]
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        slot(0, 3 * _Q, _Q, "1", depth=1),
        slot(0, Fraction(11, 12), _E, "2", depth=1),
        slot(1, Fraction(0), _E, "2", depth=1),
        *[
            slot(1, Fraction(1, 12) + index * 2 * _SIXTH, _Q, str(3 + index), depth=1)
            for index in range(4)
        ],
        slot(2, Fraction(0), _Q, "7", depth=1),
        slot(2, 2 * _SIXTH, _E, "8", depth=1),
        slot(2, _Q, _H, "rest"),
        slot(3, Fraction(0), _E, "8", depth=1),
        slot(3, _SIXTH, _Q, "9", depth=1),
        *[slot(3, Fraction(beat, 4), _Q, "0") for beat in range(1, 4)],
    ]
    assert tie_layout(score=after) == [
        TieSlot(start=(0, Fraction(11, 12), 2), end=(1, Fraction(0), 2))
    ]
    assert broken_relations(score=after) == []
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_a_tuplet_of_a_second_voice_on_an_anchor_shared_with_the_first_stays_with_it() -> None:
    """Voice two's eighth triplet on beat three shares its anchor with voice one's quarter;
    in 3/4 both stay on beat three, and both fourth beats open the added measure."""
    first, second = build_two_voices(measure_count=2)
    quarters(score=first, measure=0)
    quarters(score=first, measure=1)
    quarters(score=second, measure=0, beats=(0, 1))
    eighth_triplet(score=second, parent=second.voice, at=_H)
    quarters(score=second, measure=0, beats=(3,))
    quarters(score=second, measure=1)
    shared: TemporalAnchor = anchor_at(score=first, at=_H)

    apply_intent(
        score=first,
        intent=change_time_signature(measures=first.measures[:1], time_signature=_THREE_FOUR),
    )

    first_after: Score = refresh_score(score=first)
    second_after: Score = refresh_score(score=second)
    assert (shared.measure, shared.position.value) == (first.measures[0], _H)
    assert len(shared.containers) == 3
    assert group_spans(score=second_after) == [(0, _H, Fraction(3, 8), _Q, 0)]
    after_measure: list[Slot] = [
        slot(1, Fraction(0), _Q, "0"),
        slot(1, _Q, _H, "rest"),
        *[slot(2, Fraction(beat, 4), _Q, "0") for beat in range(4)],
    ]
    assert layout(score=first_after) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(3)],
        *after_measure,
    ]
    assert layout(score=second_after) == [
        *[slot(0, Fraction(beat, 4), _Q, "0") for beat in range(2)],
        *[slot(0, _H + index * _SIXTH, _E, str(1 + index), depth=1) for index in range(3)],
        *after_measure,
    ]
    assert orphan_anchors(score=first_after) == []


@pytest.mark.unit
@_PENDING
def test_four_four_to_two_four_on_two_measures_adds_two_measures() -> None:
    score: Score = _two_numbered_measures_and_quarters()

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:2], time_signature=_TWO_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert signatures(score=after) == [_H] * 4 + [Fraction(1)]
    assert after.measures[:2] == score.measures[:2]
    assert after.measures[4] is score.measures[2]
    assert layout(score=after) == [
        *[
            slot(measure, Fraction(beat, 4), _Q, str(1 + 2 * measure + beat))
            for measure in range(4)
            for beat in range(2)
        ],
        *[slot(4, Fraction(beat, 4), _Q, "0") for beat in range(4)],
    ]
    assert orphan_anchors(score=after) == []


@pytest.mark.unit
@_PENDING
def test_four_four_to_six_eight_keeps_the_time_and_fills_the_added_measure() -> None:
    """The fill spells the hole after the fourth quarter by its own rule, as a half rest."""
    score: Score = build_score(measure_count=2)
    numbered_quarters(score=score, measure=0, first_step=1)
    quarters(score=score, measure=1)
    six_eight: RhythmicSize = size(RhythmicValue.EIGHTH, count=6)

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:1], time_signature=six_eight),
    )

    after: Score = refresh_score(score=score)
    assert [measure.time_signature for measure in after.measures[:2]] == [six_eight] * 2
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, str(1 + beat)) for beat in range(3)],
        slot(1, Fraction(0), _Q, "4"),
        slot(1, _Q, _H, "rest"),
        *[slot(2, Fraction(beat, 4), _Q, "0") for beat in range(4)],
    ]


@pytest.mark.unit
@_PENDING
def test_four_four_to_nine_eight_fits_in_one_measure_completed_by_an_eighth_rest() -> None:
    score: Score = build_score(measure_count=2)
    numbered_quarters(score=score, measure=0, first_step=1)
    quarters(score=score, measure=1)
    nine_eight: RhythmicSize = size(RhythmicValue.EIGHTH, count=9)

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:1], time_signature=nine_eight),
    )

    after: Score = refresh_score(score=score)
    assert after.measures == score.measures
    assert signatures(score=after) == [Fraction(9, 8), Fraction(1)]
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, str(1 + beat)) for beat in range(4)],
        slot(0, Fraction(1), _E, "rest"),
        *[slot(1, Fraction(beat, 4), _Q, "0") for beat in range(4)],
    ]


@pytest.mark.unit
@_PENDING
def test_four_four_to_three_four_and_back_leaves_a_measure_of_rests() -> None:
    """Intentional: the 3/4 change adds a measure completed by a rest; turning both 3/4
    measures back into 4/4 keeps their total length, so a second 4/4 measure holds only the
    rests."""
    score: Score = build_score(measure_count=2)
    numbered_quarters(score=score, measure=0, first_step=1)
    quarters(score=score, measure=1)

    apply_intent(
        score=score,
        intent=change_time_signature(measures=score.measures[:1], time_signature=_THREE_FOUR),
    )
    three_four: Score = refresh_score(score=score)
    apply_intent(
        score=score,
        intent=change_time_signature(measures=three_four.measures[:2], time_signature=_FOUR_FOUR),
    )

    after: Score = refresh_score(score=score)
    assert signatures(score=after) == [Fraction(1)] * 3
    assert layout(score=after) == [
        *[slot(0, Fraction(beat, 4), _Q, str(1 + beat)) for beat in range(4)],
        slot(1, Fraction(0), _H, "rest"),
        slot(1, _H, _H, "rest"),
        *[slot(2, Fraction(beat, 4), _Q, "0") for beat in range(4)],
    ]
    assert orphan_anchors(score=after) == []
