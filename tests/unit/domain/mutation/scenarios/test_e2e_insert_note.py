from fractions import Fraction

import pytest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import ClefChange, Context
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import Accidental, Clef, RhythmicValue
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    Staff,
    Voice,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
)
from piano_app.domain.score.document.services.helpers import iter_leaves
from piano_app.domain.score.document.services.mutation import build_compiler
from piano_app.domain.score.document.services.mutation.compiler import (
    InsertNoteIntent,
    MutationCompiler,
)
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateClefChangeRequest,
)

from ...scene import (
    NEW_STEP,
    Piano,
    Score,
    Snapshot,
    TieSlot,
    anchor_layout,
    apply_intent,
    build_engine,
    build_piano,
    build_score,
    build_two_voices,
    eighth_triplet,
    group_layout,
    insert_note,
    layout,
    note,
    note_at,
    orphan_anchors,
    quarters,
    size,
    slot,
    snapshot,
    tie_layout,
    value,
    with_start_contexts,
)

# An insert end to end: compiled from its intent, its frames cleared and its spans placed on
# the live document, then the posts — the whole score is compared afterwards.

_Q: Fraction = Fraction(1, 4)


@pytest.mark.unit
def test_an_insert_in_the_second_voice_leaves_the_first_voice_untouched() -> None:
    """Voice one holds four quarters, voice two a whole note on the same staff. A quarter on
    beat two of voice two writes over its whole note only; it starts at the anchor voice one's
    quarter already holds there."""
    first, second = build_two_voices(measure_count=1)
    quarters(score=first, measure=0)
    note(
        score=second,
        parent=second.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.WHOLE,
        step=5,
    )
    first_before: Snapshot = snapshot(score=first)
    first_leaves: list[LeafRhythmicContainer] = iter_leaves(first.voice)

    insert_note(score=second, at=_Q, rhythmic_value=RhythmicValue.QUARTER)

    assert layout(score=second) == [
        slot(0, Fraction(0), _Q, "rest"),
        slot(0, _Q, _Q, str(NEW_STEP)),
        slot(0, Fraction(1, 2), Fraction(1, 2), "rest"),
    ]
    assert snapshot(score=first) == first_before
    assert all(
        kept is leaf for kept, leaf in zip(iter_leaves(first.voice), first_leaves, strict=True)
    )
    second_leaf = note_at(score=second, at=_Q).note_carrier.owner
    assert isinstance(second_leaf, LeafRhythmicContainer)
    assert second_leaf.anchor is first_leaves[1].anchor
    assert group_layout(score=second) == []
    assert tie_layout(score=second) == []
    assert anchor_layout(score=second) == [(0, Fraction(beat, 4)) for beat in range(4)]
    assert orphan_anchors(score=second) == []


@pytest.mark.unit
def test_a_half_on_the_last_beat_of_a_three_four_measure_is_cut_and_tied_into_the_next() -> None:
    """Measure one is 3/4 and full of quarters, measure two (4/4) is asleep. A half on beat
    three is cut at the 3/4 barline into two tied quarters; the second wakes measure two,
    whose rest is filled with a dotted half."""
    measures: list[Measure] = [
        Measure.create(time_signature=size(RhythmicValue.QUARTER, count=3)),
        Measure.create(),
    ]
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
    quarters(score=score, measure=0, beats=(0, 1, 2))

    apply_intent(
        score=score,
        intent=InsertNoteIntent(
            voice_id=voice.id,
            staff_id=staff.id,
            measure_id=measures[0].id,
            position=MeasurePosition.of_fraction(fraction=Fraction(1, 2)),
            written_value=value(RhythmicValue.HALF),
            staff_step=NEW_STEP,
            accidental=Accidental.NATURAL,
        ),
    )

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "0"),
        slot(0, Fraction(1, 2), _Q, str(NEW_STEP)),
        slot(1, Fraction(0), _Q, str(NEW_STEP)),
        slot(1, _Q, Fraction(3, 4), "rest"),
    ]
    assert tie_layout(score=score) == [
        TieSlot(start=(0, Fraction(1, 2), NEW_STEP), end=(1, Fraction(0), NEW_STEP))
    ]
    assert group_layout(score=score) == []
    assert anchor_layout(score=score) == [
        (0, Fraction(0)),
        (0, _Q),
        (0, Fraction(1, 2)),
        (1, Fraction(0)),
        (1, _Q),
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_thirty_second_whose_cut_cannot_be_spelled_restores_the_triplet_it_cleared() -> None:
    """A thirty-second 1/64 before the barline reaches the triplet opening measure two: the
    frames clear that triplet first, then the spans refuse the 1/64 cut. The refusal rolls
    the gesture back, so the very same triplet, notes and anchors are there again."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0)
    triplet: GroupRhythmicContainer = eighth_triplet(
        score=score, parent=score.voice, at=Fraction(1)
    )
    quarters(score=score, measure=1, beats=(1, 2, 3))
    before: Snapshot = snapshot(score=score)
    children: list[RhythmicContainer] = list(triplet.children)
    leaves: list[LeafRhythmicContainer] = iter_leaves(score.voice)

    with pytest.raises(MutationRejectedError, match="Cannot spell a part of 1/64"):
        insert_note(score=score, at=Fraction(63, 64), rhythmic_value=RhythmicValue.THIRTY_SECOND)

    assert snapshot(score=score) == before
    assert score.voice.children[4] is triplet
    assert all(kept is child for kept, child in zip(triplet.children, children, strict=True))
    assert all(kept is leaf for kept, leaf in zip(iter_leaves(score.voice), leaves, strict=True))


@pytest.mark.unit
def test_a_note_landing_on_an_anchor_holding_a_clef_starts_there_and_keeps_the_clef() -> None:
    """A half on beat two writes over the quarters on beats two and three. It starts at the
    anchor the old quarter and the clef shared; the clef stays, and only beat three's anchor
    is reaped."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    build_engine().process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measures[0],
                position=MeasurePosition.of_fraction(fraction=_Q),
                staff=score.staff,
                clef=Clef.BASS,
            )
        ],
    )
    clef: Context = next(
        context
        for context in score.staff.contexts
        if isinstance(context, ClefChange) and context.clef is Clef.BASS
    )
    assert isinstance(clef, ClefChange)

    insert_note(score=score, at=_Q, rhythmic_value=RhythmicValue.HALF)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, Fraction(1, 2), str(NEW_STEP)),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    leaf = note_at(score=score, at=_Q).note_carrier.owner
    assert isinstance(leaf, LeafRhythmicContainer)
    assert leaf.anchor is clef.start
    assert list(clef.start.starting_contexts) == [clef]
    assert anchor_layout(score=score) == [(0, Fraction(0)), (0, _Q), (0, Fraction(3, 4))]
    assert group_layout(score=score) == []
    assert tie_layout(score=score) == []
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_note_on_a_pitch_its_chord_already_holds_is_refused() -> None:
    """A chord cannot hold one pitch twice: the whole gesture is refused at its end and the
    score is as it was."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match="one pitch twice"):
        insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, step=0)

    assert snapshot(score=score) == before


@pytest.mark.unit
def test_a_note_on_the_pitch_its_chord_holds_in_another_clef_is_refused_too() -> None:
    """Pitch is what the notes sound like, not the step they stand on: a step of the bass
    staff that sounds as the treble note of the chord is a duplicate."""
    piano: Piano = build_piano()
    compiler: MutationCompiler = build_compiler()

    def put(*, staff: Staff, step: int) -> None:
        build_engine().process(
            document=piano.document,
            requests=compiler.compile(
                document=piano.document,
                intent=InsertNoteIntent(
                    voice_id=piano.voice.id,
                    staff_id=staff.id,
                    measure_id=piano.measures[0].id,
                    position=MeasurePosition.of(numerator=0, denominator=1),
                    written_value=value(RhythmicValue.QUARTER),
                    staff_step=step,
                    accidental=Accidental.NATURAL,
                ),
            ),
        )

    put(staff=piano.upper, step=0)

    with pytest.raises(MutationRejectedError, match="one pitch twice"):
        put(staff=piano.lower, step=12)

    assert [type(item) for item in piano.upper.musical_items if isinstance(item, Note)] == [Note]
    assert not [item for item in piano.lower.musical_items if isinstance(item, Note)]
