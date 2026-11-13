from collections.abc import Callable, Sequence
from fractions import Fraction
from typing import overload

import pytest

from piano_app.domain.score.document.models.material import Note, NoteCarrier, Rest
from piano_app.domain.score.document.models.notation import (
    Accidental,
    RhythmicValue,
)
from piano_app.domain.score.document.models.presentation import (
    PresentationTarget,
    ReferencePoint,
    VerticalOffset,
)
from piano_app.domain.score.document.models.structural import MeasurePosition, Staff, Voice
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.geometry import Span
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.compiler import (
    CreateTupletWithRestIntent,
    DeleteBatchIntent,
    EditIntent,
    InsertNoteIntent,
    TieNotesIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.engine.postprocessors import fill_gaps
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)
from piano_app.domain.score.document.services.presentation import (
    PresentationEditor,
    SetVerticalOffset,
)
from piano_app.domain.score.document.services.resolution import resolve_staff

from ...scene import (
    NEW_STEP,
    GroupSlot,
    Score,
    Slot,
    Snapshot,
    anchor_layout,
    apply_intents,
    build_score,
    build_two_voices,
    four_quarters,
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
    snapshot,
    tie_layout,
    value,
)

# Batches end to end through the editor: intent k is compiled against what intent k-1 left
# and runs as its own pass; the batch is one transaction, so any refusal rolls every intent
# before it back.

_Q: Fraction = Fraction(1, 4)
_THIRD: Fraction = Fraction(1, 12)  # one triplet eighth on the timeline
_LONGER = VerticalOffset(value=1.5)

type Step = Callable[[Score], EditIntent]


class _Addressed(Sequence[EditIntent]):
    """A batch whose intents are addressed only when the editor reaches them, so a later
    intent can name an entity an earlier one of the same batch created."""

    def __init__(self, *, score: Score, steps: Sequence[Step]) -> None:
        self._score: Score = score
        self._steps: Sequence[Step] = steps

    @overload
    def __getitem__(self, index: int) -> EditIntent: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[EditIntent]: ...

    def __getitem__(self, index: int | slice) -> EditIntent | Sequence[EditIntent]:
        if isinstance(index, slice):
            raise TypeError("A batch is addressed one intent at a time.")

        return self._steps[index](self._score)

    def __len__(self) -> int:
        return len(self._steps)


def _insert(at: Fraction, rhythmic_value: RhythmicValue, step: int = NEW_STEP) -> Step:
    return lambda score: InsertNoteIntent(
        voice_id=score.voice.id,
        staff_id=score.staff.id,
        measure_id=score.measures[int(at)].id,
        position=MeasurePosition.of_fraction(fraction=at - int(at)),
        written_value=value(rhythmic_value),
        staff_step=step,
        accidental=Accidental.NATURAL,
    )


def _tie(start: Fraction, end: Fraction) -> Step:
    return lambda score: TieNotesIntent(
        start_note_id=note_at(score=score, at=start).id,
        end_note_id=note_at(score=score, at=end).id,
    )


def _delete_note(at: Fraction) -> Step:
    return lambda score: DeleteBatchIntent(entity_ids=(note_at(score=score, at=at).id,))


@pytest.mark.unit
def test_tying_the_pieces_an_insert_just_cut_is_refused_and_rolls_the_insert_back() -> None:
    """A half on beat four is cut at the barline into two quarters already tied; tying them
    again is refused, and the insert goes with the refusal — measure two is asleep again."""
    score: Score = build_score(measure_count=2)
    quarters(score=score, measure=0, beats=(0, 1, 2))
    before: Snapshot = snapshot(score=score)

    with pytest.raises(MutationRejectedError, match="already starts another tie"):
        apply_intents(
            score=score,
            intents=_Addressed(
                score=score,
                steps=[
                    _insert(Fraction(3, 4), RhythmicValue.HALF),
                    _tie(Fraction(3, 4), Fraction(1)),
                ],
            ),
        )

    assert snapshot(score=score) == before
    assert score.measures[1].anchors == []


@pytest.mark.unit
def test_an_insert_tie_and_delete_in_one_batch_leave_the_tie_dropped_with_the_note() -> None:
    """A quarter on beat three, tied from the quarter before it, then deleted: the tie goes
    with it, its hole is refilled with a quarter rest beside the rest after it, and the
    quarter it was tied from stays untied."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0, 1))
    tied_from: Note = note_at(score=score, at=_Q)

    apply_intents(
        score=score,
        intents=_Addressed(
            score=score,
            steps=[
                # a tie joins notes of one pitch: the scene's quarters stand on step 0
                _insert(Fraction(1, 2), RhythmicValue.QUARTER, step=0),
                _tie(_Q, Fraction(1, 2)),
                _delete_note(Fraction(1, 2)),
            ],
        ),
    )

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "0"),
        slot(0, Fraction(1, 2), _Q, "rest"),
        slot(0, Fraction(3, 4), _Q, "rest"),
    ]
    assert group_layout(score=score) == []
    assert tie_layout(score=score) == []
    assert note_at(score=score, at=_Q) is tied_from
    assert list(tied_from.relations) == []
    assert anchor_layout(score=score) == [
        (0, Fraction(0)),
        (0, _Q),
        (0, Fraction(1, 2)),
        (0, Fraction(3, 4)),
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_stem_set_earlier_in_the_batch_goes_with_the_carrier_a_longer_note_replaces() -> None:
    score: Score = four_quarters()
    carrier: NoteCarrier = note_at(score=score, at=Fraction(0)).note_carrier

    PresentationEditor().apply(
        document=score.document,
        commands=[
            SetVerticalOffset(
                target=PresentationTarget(entity_id=carrier.id, reference=ReferencePoint.STEM_TIP),
                value=_LONGER,
            )
        ],
        sink=MutationLog(),
    )
    apply_intents(
        score=score,
        intents=[
            _insert(Fraction(0), RhythmicValue.HALF)(score),
        ],
    )

    assert layout(score=score) == [
        slot(0, Fraction(0), Fraction(1, 2), str(NEW_STEP)),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    replacing: NoteCarrier = note_at(score=score, at=Fraction(0)).note_carrier
    assert replacing is not carrier
    assert (
        PresentationTarget(entity_id=replacing.id, reference=ReferencePoint.STEM_TIP)
        not in score.document.presentation.vertical
    )
    assert group_layout(score=score) == []
    assert tie_layout(score=score) == []
    assert anchor_layout(score=score) == [
        (0, Fraction(0)),
        (0, Fraction(1, 2)),
        (0, Fraction(3, 4)),
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_note_inserted_by_position_lands_in_the_tuplet_created_earlier_in_the_batch() -> None:
    """An eighth triplet with its first rest on beat two, then an eighth on the triplet's
    second slot: the insert is addressed by position only, and the live document already
    holds the triplet there."""
    score: Score = four_quarters()
    triplet_with_rest: EditIntent = CreateTupletWithRestIntent(
        voice_id=score.voice.id,
        staff_id=score.staff.id,
        measure_id=score.measures[0].id,
        position=MeasurePosition.of_fraction(fraction=_Q),
        written_size=size(RhythmicValue.EIGHTH, count=3),
        occupied_size=size(RhythmicValue.QUARTER),
        written_value=value(RhythmicValue.EIGHTH),
    )

    apply_intents(
        score=score,
        intents=[triplet_with_rest, _insert(_Q + _THIRD, RhythmicValue.EIGHTH)(score)],
    )

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, Fraction(1, 8), "rest", depth=1),
        slot(0, _Q + _THIRD, Fraction(1, 8), str(NEW_STEP), depth=1),
        slot(0, _Q + 2 * _THIRD, Fraction(1, 8), "rest", depth=1),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert group_layout(score=score) == [
        GroupSlot(
            measure_index=0,
            position=_Q,
            written=size(RhythmicValue.EIGHTH, count=3),
            occupied=size(RhythmicValue.QUARTER),
            depth=0,
        )
    ]
    assert tie_layout(score=score) == []
    assert anchor_layout(score=score) == [
        (0, Fraction(0)),
        (0, _Q),
        (0, _Q + _THIRD),
        (0, _Q + 2 * _THIRD),
        (0, Fraction(1, 2)),
        (0, Fraction(3, 4)),
    ]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_a_batch_over_two_voices_edits_each_voice_on_its_own() -> None:
    """Voice one holds quarters, voice two a whole note. A half over voice one's first two
    quarters and a quarter on beat four of voice two, in one batch: beat two's anchor is
    reaped, beat four's is shared by both voices."""
    first, second = build_two_voices(measure_count=1)
    quarters(score=first, measure=0)
    note(
        score=second,
        parent=second.voice,
        at=Fraction(0),
        rhythmic_value=RhythmicValue.WHOLE,
        step=5,
    )

    apply_intents(
        score=first,
        intents=[
            _insert(Fraction(0), RhythmicValue.HALF)(first),
            _insert(Fraction(3, 4), RhythmicValue.QUARTER)(second),
        ],
    )

    assert layout(score=first) == [
        slot(0, Fraction(0), Fraction(1, 2), str(NEW_STEP)),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert layout(score=second) == [
        slot(0, Fraction(0), Fraction(3, 4), "rest"),
        slot(0, Fraction(3, 4), _Q, str(NEW_STEP)),
    ]
    first_leaf = note_at(score=first, at=Fraction(3, 4)).note_carrier.owner
    second_leaf = note_at(score=second, at=Fraction(3, 4)).note_carrier.owner
    assert isinstance(first_leaf, LeafRhythmicContainer)
    assert isinstance(second_leaf, LeafRhythmicContainer)
    assert first_leaf.anchor is second_leaf.anchor
    for voice_score in (first, second):
        assert group_layout(score=voice_score) == []
        assert tie_layout(score=voice_score) == []
    assert anchor_layout(score=first) == [
        (0, Fraction(0)),
        (0, Fraction(1, 2)),
        (0, Fraction(3, 4)),
    ]
    assert orphan_anchors(score=first) == []


@pytest.mark.unit
def test_an_empty_batch_changes_nothing() -> None:
    score: Score = four_quarters()
    before: Snapshot = snapshot(score=score)

    log: MutationLog = apply_intents(score=score, intents=[])

    assert snapshot(score=score) == before

    log.rollback()

    assert snapshot(score=score) == before


@pytest.mark.unit
def test_a_fill_refused_in_the_second_pass_rolls_back_the_first_pass_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A quarter rest, then three quarter notes. Intent one deletes beat two and its hole is
    refilled with a quarter rest. Intent two deletes beat four, and the staff for that hole
    is refused here. The refusal is reached only once intent one has left its rest, and it
    rolls both intents back, the original rest included."""
    score: Score = build_score(measure_count=1)
    rest(score=score, parent=score.voice, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)
    quarters(score=score, measure=0, beats=(1, 2, 3))
    before: Snapshot = snapshot(score=score)
    original: Rest = rest_at(score=score, at=Fraction(0))
    seen_at_refusal: list[list[Slot]] = []

    def refuse(*, geometry: ScoreGeometry, voice: Voice, gap: Span) -> Staff:
        # only the hole of beat four is refused; every other hole is resolved as usual
        if gap.start_point.to(frame=geometry.root).value != Fraction(3, 4):
            return resolve_staff(geometry=geometry, voice=voice, gap=gap)
        seen_at_refusal.append(layout(score=score))
        raise ValueError("No staff for this gap.")

    monkeypatch.setattr(fill_gaps, "resolve_staff", refuse)

    with pytest.raises(MutationRejectedError, match="No staff for this gap"):
        apply_intents(
            score=score,
            intents=_Addressed(score=score, steps=[_delete_note(_Q), _delete_note(Fraction(3, 4))]),
        )

    assert seen_at_refusal == [
        [
            slot(0, Fraction(0), _Q, "rest"),
            slot(0, _Q, _Q, "rest"),
            slot(0, Fraction(1, 2), _Q, "0"),
        ]
    ]
    assert snapshot(score=score) == before
    assert rest_at(score=score, at=Fraction(0)) is original
