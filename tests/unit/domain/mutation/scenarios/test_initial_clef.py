from collections.abc import Sequence
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import ClefChange, Context, StaffScoped
from piano_app.domain.score.document.models.notation import Clef, RhythmicSize, RhythmicValue
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    Staff,
    Voice,
)
from piano_app.domain.score.document.services.mutation import build_compiler
from piano_app.domain.score.document.services.mutation.compiler import (
    DeleteBatchIntent,
    EditIntent,
    InsertMeasureIntent,
)
from piano_app.domain.score.document.services.mutation.engine.factory import build_engine
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateClefChangeRequest,
    CreateKeySignatureChangeRequest,
)

from ...scene import size

# The clef at the very start of every staff (initial-clef-invariant), driven through the
# production engine. The scene's own engine checks geometry with an API that no longer exists.

_Q: Fraction = Fraction(1, 4)
_START: Fraction = Fraction(0)

type ContextSlot = tuple[int, Fraction, str, int]


def _document(*, time_signatures: Sequence[RhythmicSize]) -> ScoreDocument:
    return ScoreDocument.create(
        voices=[Voice()],
        staffs=[Staff(), Staff()],
        measures=[Measure.create(time_signature=signature) for signature in time_signatures],
    )


def _four_four() -> RhythmicSize:
    return size(RhythmicValue.QUARTER, 4)


def _position(*, at: Fraction) -> MeasurePosition:
    return MeasurePosition.of_fraction(fraction=at)


def _put_clef(
    *,
    document: ScoreDocument,
    staff: Staff,
    measure: int,
    at: Fraction,
    clef: Clef = Clef.TREBLE,
) -> ClefChange:
    build_engine().process(
        document=document,
        requests=[
            CreateClefChangeRequest(
                measure=document.measures[measure],
                position=_position(at=at),
                staff=staff,
                clef=clef,
            )
        ],
    )
    clef_change: Context | None = next(
        (
            context
            for context in staff.contexts
            if context.start.measure is document.measures[measure]
            and context.start.position == _position(at=at)
        ),
        None,
    )
    assert isinstance(clef_change, ClefChange)

    return clef_change


def _put_key_signature(*, document: ScoreDocument, staff: Staff) -> None:
    build_engine().process(
        document=document,
        requests=[
            CreateKeySignatureChangeRequest(
                measure=document.measures[0],
                position=_position(at=_START),
                staff=staff,
            )
        ],
    )


def _apply(*, document: ScoreDocument, intent: EditIntent) -> None:
    build_engine().process(
        document=document,
        requests=build_compiler().compile(document=document, intent=intent),
    )


def _contexts(*, document: ScoreDocument) -> list[ContextSlot]:
    """Every context as (measure index, position, kind, staff index), sorted: the order of
    contexts sharing an anchor is not part of the contract."""
    slots: list[ContextSlot] = []
    for index, measure in enumerate(document.measures):
        for anchor in measure.anchors:
            for context in anchor.starting_contexts:
                assert isinstance(context, StaffScoped)
                slots.append(
                    (
                        index,
                        anchor.position.value,
                        type(context).__name__,
                        document.staffs.index(context.staff),
                    )
                )

    return sorted(slots)


def _initial_clefs(*, document: ScoreDocument) -> list[Clef]:
    """The clef of each staff at the start of the score; fails for a staff without one."""
    first: Measure = document.measures[0]
    clefs: list[Clef] = []
    for staff in document.staffs:
        found: list[ClefChange] = [
            context
            for context in staff.contexts
            if isinstance(context, ClefChange)
            and context.start.measure is first
            and context.start.position == _position(at=_START)
        ]
        assert len(found) == 1
        clefs.append(found[0].clef)

    return clefs


@pytest.mark.unit
def test_inserting_before_the_first_measure_moves_the_initial_clef_and_key_signature() -> None:
    document: ScoreDocument = _document(time_signatures=[_four_four(), _four_four()])
    first, second = document.staffs
    _put_clef(document=document, staff=first, measure=0, at=_START, clef=Clef.TREBLE)
    _put_clef(document=document, staff=second, measure=0, at=_START, clef=Clef.BASS)
    _put_clef(document=document, staff=first, measure=0, at=_Q, clef=Clef.BASS)
    _put_key_signature(document=document, staff=first)
    old_first: Measure = document.measures[0]

    _apply(document=document, intent=InsertMeasureIntent(before_measure_id=old_first.id))

    assert document.measures[1] is old_first
    assert _initial_clefs(document=document) == [Clef.TREBLE, Clef.BASS]
    assert _contexts(document=document) == [
        (0, _START, "ClefChange", 0),
        (0, _START, "ClefChange", 1),
        (0, _START, "KeySignatureChange", 0),
        (1, _Q, "ClefChange", 0),
    ]
    assert not any(anchor.position.value == _START for anchor in old_first.anchors)


@pytest.mark.unit
def test_the_measure_inserted_before_the_first_takes_the_next_time_signature() -> None:
    three_four: RhythmicSize = size(RhythmicValue.QUARTER, 3)
    document: ScoreDocument = _document(time_signatures=[three_four, _four_four()])

    _apply(
        document=document,
        intent=InsertMeasureIntent(before_measure_id=document.measures[0].id),
    )

    assert [measure.time_signature for measure in document.measures] == [
        three_four,
        three_four,
        _four_four(),
    ]


@pytest.mark.unit
def test_inserting_between_measures_leaves_every_context_in_place() -> None:
    document: ScoreDocument = _document(time_signatures=[_four_four(), _four_four(), _four_four()])
    first, second = document.staffs
    _put_clef(document=document, staff=first, measure=0, at=_START)
    _put_clef(document=document, staff=second, measure=0, at=_START, clef=Clef.BASS)
    _put_clef(document=document, staff=first, measure=1, at=_START, clef=Clef.BASS)

    _apply(
        document=document,
        intent=InsertMeasureIntent(before_measure_id=document.measures[1].id),
    )

    assert _contexts(document=document) == [
        (0, _START, "ClefChange", 0),
        (0, _START, "ClefChange", 1),
        (2, _START, "ClefChange", 0),
    ]


@pytest.mark.unit
def test_a_delete_batch_naming_the_initial_clef_is_refused_and_changes_nothing() -> None:
    document: ScoreDocument = _document(time_signatures=[_four_four()])
    initial: ClefChange = _put_clef(
        document=document, staff=document.staffs[0], measure=0, at=_START
    )
    before: list[ContextSlot] = _contexts(document=document)

    with pytest.raises(MutationRejectedError, match="start of the score"):
        _apply(document=document, intent=DeleteBatchIntent(entity_ids=(initial.id,)))

    assert _contexts(document=document) == before
    assert list(document.staffs[0].contexts) == [initial]


@pytest.mark.unit
def test_a_delete_batch_naming_the_initial_clef_and_its_measure_is_refused() -> None:
    document: ScoreDocument = _document(time_signatures=[_four_four(), _four_four()])
    initial: ClefChange = _put_clef(
        document=document, staff=document.staffs[0], measure=0, at=_START
    )
    before: list[ContextSlot] = _contexts(document=document)

    with pytest.raises(MutationRejectedError, match="start of the score"):
        _apply(
            document=document,
            intent=DeleteBatchIntent(entity_ids=(document.measures[0].id, initial.id)),
        )

    assert len(document.measures) == 2
    assert _contexts(document=document) == before


@pytest.mark.unit
def test_a_delete_batch_naming_a_clef_elsewhere_is_refused() -> None:
    """A clef has a command of its own, which asks how its notes are treated."""
    document: ScoreDocument = _document(time_signatures=[_four_four(), _four_four()])
    staff: Staff = document.staffs[0]
    initial: ClefChange = _put_clef(document=document, staff=staff, measure=0, at=_START)
    later: ClefChange = _put_clef(
        document=document, staff=staff, measure=1, at=_START, clef=Clef.BASS
    )

    with pytest.raises(MutationRejectedError, match="its own command"):
        _apply(document=document, intent=DeleteBatchIntent(entity_ids=(later.id,)))

    assert list(staff.contexts) == [initial, later]


@pytest.mark.unit
def test_a_new_clef_at_the_start_replaces_the_initial_one() -> None:
    document: ScoreDocument = _document(time_signatures=[_four_four()])
    staff: Staff = document.staffs[0]
    _put_clef(document=document, staff=staff, measure=0, at=_START, clef=Clef.TREBLE)
    _put_clef(document=document, staff=document.staffs[1], measure=0, at=_START, clef=Clef.TREBLE)

    _put_clef(document=document, staff=staff, measure=0, at=_START, clef=Clef.BASS)

    assert _initial_clefs(document=document) == [Clef.BASS, Clef.TREBLE]


@pytest.mark.unit
def test_removing_the_first_measure_moves_the_initial_clef_to_the_next_one() -> None:
    document: ScoreDocument = _document(time_signatures=[_four_four(), _four_four()])
    first, second = document.staffs
    clef: ClefChange = _put_clef(document=document, staff=first, measure=0, at=_START)
    _put_clef(document=document, staff=second, measure=0, at=_START, clef=Clef.BASS)
    next_measure: Measure = document.measures[1]

    _apply(document=document, intent=DeleteBatchIntent(entity_ids=(document.measures[0].id,)))

    assert list(document.measures) == [next_measure]
    assert clef.start.measure is next_measure
    assert _initial_clefs(document=document) == [Clef.TREBLE, Clef.BASS]


@pytest.mark.unit
def test_removing_the_first_measure_keeps_the_clef_the_next_one_already_has() -> None:
    document: ScoreDocument = _document(time_signatures=[_four_four(), _four_four()])
    staff: Staff = document.staffs[0]
    _put_clef(document=document, staff=staff, measure=0, at=_START, clef=Clef.TREBLE)
    _put_clef(document=document, staff=document.staffs[1], measure=0, at=_START)
    own: ClefChange = _put_clef(
        document=document, staff=staff, measure=1, at=_START, clef=Clef.BASS
    )

    _apply(document=document, intent=DeleteBatchIntent(entity_ids=(document.measures[0].id,)))

    assert list(staff.contexts) == [own]
    assert _initial_clefs(document=document) == [Clef.BASS, Clef.TREBLE]
