from dataclasses import dataclass

import pytest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import (
    ClefChange,
    KeySignatureChange,
    OctaveTransposition,
)
from piano_app.domain.score.document.models.notation import Clef
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition, Staff, Voice
from piano_app.domain.score.document.services.mutation import MutationEngine
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateClefChangeRequest,
    CreateKeySignatureChangeRequest,
    CreateOctaveTranspositionRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)

from ..scene import build_engine


@dataclass(frozen=True, slots=True, kw_only=True)
class _Score:
    document: ScoreDocument
    measure: Measure
    staff_a: Staff
    staff_b: Staff


@pytest.fixture
def score() -> _Score:
    measure: Measure = Measure.create()
    staff_a, staff_b = Staff(), Staff()
    document: ScoreDocument = ScoreDocument.create(
        voices=[Voice()], staffs=[staff_a, staff_b], measures=[measure]
    )

    return _Score(document=document, measure=measure, staff_a=staff_a, staff_b=staff_b)


@pytest.fixture
def engine() -> MutationEngine:
    return build_engine()


@pytest.mark.unit
def test_a_clef_change_creates_its_own_anchor(score: _Score, engine: MutationEngine) -> None:
    log = engine.process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measure,
                position=MeasurePosition.of(numerator=1, denominator=4),
                staff=score.staff_a,
                clef=Clef.BASS,
            )
        ],
    )

    assert len(score.measure.anchors) == 1
    anchor = score.measure.anchors[0]
    assert anchor.position == MeasurePosition.of(numerator=1, denominator=4)
    assert len(anchor.starting_contexts) == 1
    clef_change = anchor.starting_contexts[0]
    assert isinstance(clef_change, ClefChange)
    assert clef_change.clef is Clef.BASS and clef_change.staff is score.staff_a

    log.rollback()
    assert score.measure.anchors == []


@pytest.mark.unit
def test_a_second_clef_change_at_the_same_anchor_and_staff_displaces_the_first(
    score: _Score,
    engine: MutationEngine,
) -> None:
    """The invariant: two ClefChange for the same staff at the same anchor cannot
    coexist — the second replaces the first rather than erroring."""
    position = MeasurePosition.of(numerator=0, denominator=1)
    engine.process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measure,
                position=position,
                staff=score.staff_a,
                clef=Clef.TREBLE,
            )
        ],
    )
    anchor = score.measure.anchors[0]
    first = anchor.starting_contexts[0]

    engine.process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measure,
                position=position,
                staff=score.staff_a,
                clef=Clef.BASS,
            )
        ],
    )

    # no new anchor -- the existing one was reused
    assert len(score.measure.anchors) == 1
    assert len(anchor.starting_contexts) == 1
    survivor = anchor.starting_contexts[0]
    assert isinstance(survivor, ClefChange)
    assert survivor.clef is Clef.BASS
    assert survivor is not first


@pytest.mark.unit
def test_clef_changes_on_different_staffs_at_the_same_anchor_coexist(
    score: _Score,
    engine: MutationEngine,
) -> None:
    position = MeasurePosition.of(numerator=0, denominator=1)
    engine.process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measure,
                position=position,
                staff=score.staff_a,
                clef=Clef.TREBLE,
            )
        ],
    )
    engine.process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measure,
                position=position,
                staff=score.staff_b,
                clef=Clef.BASS,
            )
        ],
    )

    anchor = score.measure.anchors[0]
    assert {ctx.staff for ctx in anchor.starting_contexts if isinstance(ctx, ClefChange)} == {
        score.staff_a,
        score.staff_b,
    }


@pytest.mark.unit
def test_a_clef_change_and_a_key_signature_change_at_the_same_anchor_and_staff_coexist(
    score: _Score,
    engine: MutationEngine,
) -> None:
    """Different types don't conflict -- the invariant is per concrete type, not
    "one context per anchor+staff"."""
    position = MeasurePosition.of(numerator=0, denominator=1)
    engine.process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measure,
                position=position,
                staff=score.staff_a,
                clef=Clef.TREBLE,
            )
        ],
    )
    engine.process(
        document=score.document,
        requests=[
            CreateKeySignatureChangeRequest(
                measure=score.measure,
                position=position,
                staff=score.staff_a,
            )
        ],
    )

    anchor = score.measure.anchors[0]
    kinds = {type(ctx) for ctx in anchor.starting_contexts}
    assert kinds == {ClefChange, KeySignatureChange}


@pytest.mark.unit
def test_a_second_key_signature_change_displaces_the_first(
    score: _Score,
    engine: MutationEngine,
) -> None:
    position = MeasurePosition.of(numerator=0, denominator=1)
    engine.process(
        document=score.document,
        requests=[
            CreateKeySignatureChangeRequest(
                measure=score.measure,
                position=position,
                staff=score.staff_a,
            )
        ],
    )
    engine.process(
        document=score.document,
        requests=[
            CreateKeySignatureChangeRequest(
                measure=score.measure,
                position=position,
                staff=score.staff_a,
            )
        ],
    )

    anchor = score.measure.anchors[0]
    key_signature_changes = [
        ctx for ctx in anchor.starting_contexts if isinstance(ctx, KeySignatureChange)
    ]
    assert len(key_signature_changes) == 1


@pytest.mark.unit
def test_deleting_a_context_goes_through_the_generic_path_and_leaves_no_orphan(
    score: _Score,
    engine: MutationEngine,
) -> None:
    """Delete is generic over Context (mirrors DeleteRequest over Relation),
    and the anchor's own orphan cleanup already accounts for context lists."""
    engine.process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measure,
                position=MeasurePosition.of(numerator=0, denominator=1),
                staff=score.staff_a,
                clef=Clef.TREBLE,
            )
        ],
    )
    clef_change = score.measure.anchors[0].starting_contexts[0]

    engine.process(document=score.document, requests=[DeleteRequest(target=clef_change)])

    # the cleanup postprocessor reaps the now-orphan anchor
    assert score.measure.anchors == []


@pytest.mark.unit
def test_a_second_clef_change_at_a_different_position_gets_its_own_anchor(
    score: _Score,
    engine: MutationEngine,
) -> None:
    engine.process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measure,
                position=MeasurePosition.of(numerator=0, denominator=1),
                staff=score.staff_a,
                clef=Clef.TREBLE,
            )
        ],
    )
    engine.process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measure,
                position=MeasurePosition.of(numerator=1, denominator=2),
                staff=score.staff_a,
                clef=Clef.BASS,
            )
        ],
    )

    assert len(score.measure.anchors) == 2
    clefs: list[Clef] = []
    for anchor in score.measure.anchors:
        for context in anchor.starting_contexts:
            assert isinstance(context, ClefChange)
            clefs.append(context.clef)
    assert clefs == [Clef.TREBLE, Clef.BASS]


# --- octave transpositions --------------------------------------------------------------


def _octave_transposition(
    *,
    score: _Score,
    staff: Staff,
    start: MeasurePosition,
    end: MeasurePosition,
) -> CreateOctaveTranspositionRequest:
    return CreateOctaveTranspositionRequest(
        start_measure=score.measure,
        start_position=start,
        end_measure=score.measure,
        end_position=end,
        staff=staff,
        octaves=1,
    )


_BEAT_ONE: MeasurePosition = MeasurePosition.of(numerator=0, denominator=1)
_BEAT_TWO: MeasurePosition = MeasurePosition.of(numerator=1, denominator=4)
_BEAT_THREE: MeasurePosition = MeasurePosition.of(numerator=1, denominator=2)
_BEAT_FOUR: MeasurePosition = MeasurePosition.of(numerator=3, denominator=4)


@pytest.mark.unit
def test_an_octave_transposition_creates_an_anchor_at_each_end(
    score: _Score,
    engine: MutationEngine,
) -> None:
    log = engine.process(
        document=score.document,
        requests=[
            _octave_transposition(
                score=score, staff=score.staff_a, start=_BEAT_ONE, end=_BEAT_THREE
            )
        ],
    )

    start, end = score.measure.anchors
    assert (start.position, end.position) == (_BEAT_ONE, _BEAT_THREE)
    transposition = score.staff_a.contexts[0]
    assert isinstance(transposition, OctaveTransposition)
    assert (transposition.start, transposition.end) == (start, end)
    assert transposition.octaves == 1
    assert list(start.starting_contexts) == [transposition]
    assert list(end.ending_contexts) == [transposition]

    log.rollback()

    assert score.measure.anchors == []
    assert list(score.staff_a.contexts) == []


@pytest.mark.unit
def test_touching_octave_transpositions_coexist_and_share_the_anchor_between_them(
    score: _Score,
    engine: MutationEngine,
) -> None:
    for start, end in ((_BEAT_ONE, _BEAT_THREE), (_BEAT_THREE, _BEAT_FOUR)):
        engine.process(
            document=score.document,
            requests=[
                _octave_transposition(score=score, staff=score.staff_a, start=start, end=end)
            ],
        )

    assert [anchor.position for anchor in score.measure.anchors] == [
        _BEAT_ONE,
        _BEAT_THREE,
        _BEAT_FOUR,
    ]
    shared = score.measure.anchors[1]
    assert len(shared.ending_contexts) == 1
    assert len(shared.starting_contexts) == 1
    assert len(score.staff_a.contexts) == 2


@pytest.mark.unit
def test_an_overlapping_octave_transposition_on_the_same_staff_is_refused(
    score: _Score,
    engine: MutationEngine,
) -> None:
    """Two overlapping brackets have no single replacement: the second is refused, not
    displaced, and creates nothing."""
    engine.process(
        document=score.document,
        requests=[
            _octave_transposition(
                score=score, staff=score.staff_a, start=_BEAT_ONE, end=_BEAT_THREE
            )
        ],
    )
    first = score.staff_a.contexts[0]
    anchors = list(score.measure.anchors)

    with pytest.raises(MutationRejectedError, match="cannot overlap another"):
        engine.process(
            document=score.document,
            requests=[
                _octave_transposition(
                    score=score, staff=score.staff_a, start=_BEAT_TWO, end=_BEAT_FOUR
                )
            ],
        )

    assert list(score.staff_a.contexts) == [first]
    assert list(score.measure.anchors) == anchors


@pytest.mark.unit
def test_the_same_octave_transposition_on_another_staff_coexists(
    score: _Score,
    engine: MutationEngine,
) -> None:
    for staff in (score.staff_a, score.staff_b):
        engine.process(
            document=score.document,
            requests=[
                _octave_transposition(score=score, staff=staff, start=_BEAT_ONE, end=_BEAT_THREE)
            ],
        )

    assert len(score.staff_a.contexts) == 1
    assert len(score.staff_b.contexts) == 1
    assert len(score.measure.anchors) == 2


@pytest.mark.unit
@pytest.mark.parametrize("end", [_BEAT_TWO, _BEAT_ONE], ids=["before its start", "at its start"])
def test_an_octave_transposition_ending_where_it_could_not_have_started_is_refused(
    score: _Score,
    engine: MutationEngine,
    end: MeasurePosition,
) -> None:
    with pytest.raises(MutationRejectedError, match="must end after it starts"):
        engine.process(
            document=score.document,
            requests=[
                _octave_transposition(score=score, staff=score.staff_a, start=_BEAT_TWO, end=end)
            ],
        )

    assert score.measure.anchors == []


@pytest.mark.unit
def test_deleting_an_octave_transposition_reaps_only_the_anchor_nothing_else_holds(
    score: _Score,
    engine: MutationEngine,
) -> None:
    """The second of two touching brackets goes: its end anchor holds nothing else and is
    reaped; its start anchor is still where the first bracket ends."""
    for start, end in ((_BEAT_ONE, _BEAT_THREE), (_BEAT_THREE, _BEAT_FOUR)):
        engine.process(
            document=score.document,
            requests=[
                _octave_transposition(score=score, staff=score.staff_a, start=start, end=end)
            ],
        )
    first, second = score.staff_a.contexts

    engine.process(document=score.document, requests=[DeleteRequest(target=second)])

    assert list(score.staff_a.contexts) == [first]
    assert [anchor.position for anchor in score.measure.anchors] == [_BEAT_ONE, _BEAT_THREE]
    assert list(score.measure.anchors[1].starting_contexts) == []
