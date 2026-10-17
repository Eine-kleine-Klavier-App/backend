from collections.abc import Sequence
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.material import Note, NoteCarrier, Rest, RestCarrier
from piano_app.domain.score.document.models.notation import Accidental, RhythmicValue
from piano_app.domain.score.document.models.structural import MeasurePosition, TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.mutation import build_engine
from piano_app.domain.score.document.services.mutation.engine.buffer import EmitBuffer
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.engine.postprocessors.cleanup import (
    CleanupPostprocessor,
)
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
    ResultRef,
)
from piano_app.domain.score.document.services.mutation.instructions.actions.temporal import (
    CreateTemporalAnchorAction,
    DeleteTemporalAnchorAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    CreateNoteRequest,
    DeleteNoteCarrierRequest,
    DeleteNoteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    DeleteLeafRequest,
    DeleteRhythmicGroupRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.temporal import (
    CreateTemporalAnchorRequest,
    DeleteTemporalAnchorRequest,
)

from ..scene import (
    NEW_STEP,
    Score,
    anchor_at,
    build_score,
    eighth_triplet,
    group,
    layout,
    note,
    orphan_anchors,
    quarters,
    size,
    slot,
    value,
)

_Q: Fraction = Fraction(1, 4)
_E: Fraction = Fraction(1, 8)


def _create_note(
    *,
    score: Score,
    scope: GroupRhythmicContainer | None = None,
    at: Fraction,
    rhythmic_value: RhythmicValue,
) -> MutationLog:
    """One create-note request sent straight to the engine, in the scope given (the
    voice when none is)."""
    return build_engine().process(
        document=score.document,
        requests=[
            CreateNoteRequest(
                scope=score.voice if scope is None else scope,
                staff=score.staff,
                measure=score.measures[int(at)],
                position=MeasurePosition.of_fraction(fraction=at - int(at)),
                written_value=value(rhythmic_value),
                staff_step=NEW_STEP,
                accidental=Accidental.NATURAL,
                out=ResultRef[Note](),
            )
        ],
    )


def _process(*, score: Score, requests: list[MutationRequest]) -> MutationLog:
    return build_engine().process(document=score.document, requests=requests)


# --- EmitBuffer: an analyzer emits only its own terminal ------------------------------


def _anchor_request(*, score: Score) -> CreateTemporalAnchorRequest:
    return CreateTemporalAnchorRequest(
        measure=score.measures[0],
        position=MeasurePosition.of(numerator=0, denominator=1),
        out=ResultRef[TemporalAnchor](),
    )


@pytest.mark.unit
def test_the_buffer_accepts_the_requests_own_terminal_and_any_sub_requests() -> None:
    score: Score = build_score(bars=1)
    request: CreateTemporalAnchorRequest = _anchor_request(score=score)
    buffer: EmitBuffer = EmitBuffer(request=request)

    buffer.incorporate(item=_anchor_request(score=score))
    buffer.incorporate(
        item=CreateTemporalAnchorAction(
            measure=request.measure,
            position=request.position,
            out=request.out,
        )
    )
    buffer.verify_complete()

    assert len(buffer.items) == 2


@pytest.mark.unit
def test_the_buffer_refuses_an_action_producing_another_entity() -> None:
    score: Score = build_score(bars=1)
    request: CreateTemporalAnchorRequest = _anchor_request(score=score)
    buffer: EmitBuffer = EmitBuffer(request=request)

    with pytest.raises(ValueError, match="out mismatch"):
        buffer.incorporate(
            item=CreateTemporalAnchorAction(
                measure=request.measure,
                position=request.position,
                out=ResultRef[TemporalAnchor](),
            )
        )


@pytest.mark.unit
def test_the_buffer_refuses_an_action_of_another_kind() -> None:
    score: Score = build_score(bars=1)
    anchor: TemporalAnchor = anchor_at(score=score, at=Fraction(0))
    buffer: EmitBuffer = EmitBuffer(request=_anchor_request(score=score))

    with pytest.raises(ValueError, match="kind"):
        buffer.incorporate(item=DeleteTemporalAnchorAction(target=anchor))


@pytest.mark.unit
def test_the_buffer_refuses_a_delete_action_targeting_another_entity() -> None:
    score: Score = build_score(bars=1)
    first: TemporalAnchor = anchor_at(score=score, at=Fraction(0))
    second: TemporalAnchor = anchor_at(score=score, at=_Q)
    buffer: EmitBuffer = EmitBuffer(request=DeleteTemporalAnchorRequest(target=first))

    with pytest.raises(ValueError, match="target mismatch"):
        buffer.incorporate(item=DeleteTemporalAnchorAction(target=second))


@pytest.mark.unit
def test_the_buffer_refuses_a_second_action() -> None:
    score: Score = build_score(bars=1)
    anchor: TemporalAnchor = anchor_at(score=score, at=Fraction(0))
    buffer: EmitBuffer = EmitBuffer(request=DeleteTemporalAnchorRequest(target=anchor))
    buffer.incorporate(item=DeleteTemporalAnchorAction(target=anchor))

    with pytest.raises(ValueError, match="only one action"):
        buffer.incorporate(item=DeleteTemporalAnchorAction(target=anchor))


@pytest.mark.unit
def test_a_create_request_expanded_without_its_terminal_is_incomplete() -> None:
    score: Score = build_score(bars=1)
    buffer: EmitBuffer = EmitBuffer(request=_anchor_request(score=score))
    buffer.incorporate(item=_anchor_request(score=score))

    with pytest.raises(ValueError, match="without its terminal"):
        buffer.verify_complete()


@pytest.mark.unit
def test_a_delete_request_may_end_without_a_terminal() -> None:
    """Only a create promises an entity to its consumers."""
    score: Score = build_score(bars=1)
    anchor: TemporalAnchor = anchor_at(score=score, at=Fraction(0))
    buffer: EmitBuffer = EmitBuffer(request=DeleteTemporalAnchorRequest(target=anchor))

    buffer.verify_complete()


# --- the create chain with an explicit scope ----------------------------------------


@pytest.mark.unit
def test_a_note_in_an_empty_voice_builds_the_whole_chain_and_the_bar_is_tiled() -> None:
    score: Score = build_score(bars=2)

    _create_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "rest"),
        slot(0, _Q, _Q, str(NEW_STEP)),
        slot(0, Fraction(1, 2), Fraction(1, 2), "rest"),
    ]
    # the second bar is never reached, so it stays asleep
    assert score.measures[1].anchors == []


@pytest.mark.unit
def test_a_note_goes_into_the_group_its_request_names() -> None:
    """The analyzers never descend on their own: the scope comes with the request, and
    the rest of the group's room is filled in the group's units."""
    score: Score = build_score(bars=1)
    triplet: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )

    _create_note(score=score, scope=triplet, at=Fraction(0), rhythmic_value=RhythmicValue.EIGHTH)

    assert layout(score=score) == [
        slot(0, Fraction(0), _E, str(NEW_STEP), depth=1),
        slot(0, Fraction(1, 12), _Q, "rest", depth=1),
        slot(0, _Q, Fraction(3, 4), "rest"),
    ]


@pytest.mark.unit
def test_a_note_on_a_same_size_note_joins_it_as_a_chord() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)

    _create_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER)

    assert [entry.content for entry in layout(score=score)] == ["0", f"0,{NEW_STEP}", "0", "0"]


@pytest.mark.unit
def test_a_group_hit_at_voice_level_is_displaced_whole() -> None:
    """A half from beat two meets the triplet and the quarter after it: both go, with
    every inner note, and nothing is left on the triplet's inner anchors."""
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0, beats=(0,))
    eighth_triplet(score=score, parent=score.voice, at=_Q)
    quarters(score=score, bar=0, beats=(2, 3))

    _create_note(score=score, at=_Q, rhythmic_value=RhythmicValue.HALF)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, Fraction(1, 2), str(NEW_STEP)),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert orphan_anchors(score=score) == []
    assert [anchor.position.value for anchor in score.measures[0].anchors] == [
        Fraction(0),
        _Q,
        Fraction(3, 4),
    ]


@pytest.mark.unit
def test_a_second_leaf_at_one_slot_replaces_the_first_rather_than_joining_it() -> None:
    """At most one container per scope starts at an anchor: a different size at an
    occupied slot displaces what was there."""
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)

    _create_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.HALF)

    anchor: TemporalAnchor = score.measures[0].anchors[0]
    assert [container.parent for container in anchor.containers] == [score.voice]
    assert layout(score=score)[0] == slot(0, Fraction(0), Fraction(1, 2), str(NEW_STEP))


# --- deletion cascade -----------------------------------------------------------------


@pytest.mark.unit
def test_deleting_a_group_deletes_every_container_inside_it_at_every_depth() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0, beats=(0, 2, 3))
    outer: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=_Q,
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    inner: GroupRhythmicContainer = group(
        score=score,
        parent=outer,
        at=_Q,
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
    )
    for index in range(3):
        note(
            score=score,
            parent=inner,
            at=_Q + Fraction(index, 36),
            rhythmic_value=RhythmicValue.SIXTEENTH,
            step=1,
        )
    for index in (1, 2):
        note(
            score=score,
            parent=outer,
            at=_Q + Fraction(index, 12),
            rhythmic_value=RhythmicValue.EIGHTH,
            step=2,
        )

    _process(score=score, requests=[DeleteRhythmicGroupRequest(target=outer)])

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "rest"),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert orphan_anchors(score=score) == []
    assert len(score.measures[0].anchors) == 4


@pytest.mark.unit
def test_deleting_an_anchor_shared_by_nested_containers_deletes_each_once() -> None:
    """Outer group, inner group and leaf all start here; only the outermost is deleted
    by the anchor — the rest goes with it, never twice."""
    score: Score = build_score(bars=1)
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
    note(score=score, parent=inner, at=Fraction(0), rhythmic_value=RhythmicValue.SIXTEENTH, step=1)
    quarters(score=score, bar=0, beats=(1, 2, 3))
    anchor: TemporalAnchor = anchor_at(score=score, at=Fraction(0))

    _process(score=score, requests=[DeleteTemporalAnchorRequest(target=anchor)])

    assert anchor not in score.measures[0].anchors
    assert layout(score=score)[0] == slot(0, Fraction(0), _Q, "rest")
    assert not any(entry.depth for entry in layout(score=score))


@pytest.mark.unit
def test_deleting_a_note_of_a_chord_keeps_the_carrier() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)
    _create_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)
    carrier = score.voice.children[0]
    assert isinstance(carrier, LeafRhythmicContainer)
    assert isinstance(carrier.carrier, NoteCarrier)
    added: Note = carrier.carrier.notes[-1]

    _process(score=score, requests=[DeleteNoteRequest(target=added)])

    assert [entry.content for entry in layout(score=score)] == ["0", "0", "0", "0"]


@pytest.mark.unit
def test_deleting_the_only_note_unwinds_carrier_leaf_and_refills_with_a_rest() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)
    leaf = score.voice.children[1]
    assert isinstance(leaf, LeafRhythmicContainer)
    assert isinstance(leaf.carrier, NoteCarrier)

    _process(score=score, requests=[DeleteNoteRequest(target=leaf.carrier.notes[0])])

    assert [entry.content for entry in layout(score=score)] == ["0", "rest", "0", "0"]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_deleting_a_carrier_cascades_down_to_its_notes() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)
    leaf = score.voice.children[3]
    assert isinstance(leaf, LeafRhythmicContainer)
    assert isinstance(leaf.carrier, NoteCarrier)
    gone: Note = leaf.carrier.notes[0]

    _process(score=score, requests=[DeleteNoteCarrierRequest(target=leaf.carrier)])

    assert gone not in score.staff.musical_items
    assert [entry.content for entry in layout(score=score)] == ["0", "0", "0", "rest"]


# --- cleanup: the childless rules -----------------------------------------------------


@pytest.mark.unit
def test_cleanup_reports_each_childless_level_including_an_empty_group() -> None:
    """An empty group is childless scaffolding like the rest; a group holding only rests is
    valid and stays."""
    score: Score = build_score(bars=2)
    empty: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(0),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    bare: LeafRhythmicContainer = LeafRhythmicContainer.create(
        parent=score.voice,
        anchor=anchor_at(score=score, at=_Q),
        size=size(RhythmicValue.QUARTER),
    )
    emptied: LeafRhythmicContainer = note(
        score=score,
        parent=score.voice,
        at=Fraction(1, 2),
        rhythmic_value=RhythmicValue.QUARTER,
        step=0,
    )
    assert isinstance(emptied.carrier, NoteCarrier)
    emptied.carrier.notes[0].detach()
    orphan: TemporalAnchor = anchor_at(score=score, at=Fraction(3, 4))
    of_rests: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(1),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    for index in range(3):
        Rest.create(
            rest_carrier=RestCarrier.create(
                owner=LeafRhythmicContainer.create(
                    parent=of_rests,
                    anchor=anchor_at(score=score, at=1 + Fraction(index, 12)),
                    size=size(RhythmicValue.EIGHTH),
                )
            ),
            staff=score.staff,
        )

    fixes: Sequence[MutationRequest] = CleanupPostprocessor().search_fixes(document=score.document)

    targets: list[object] = []
    for fix in fixes:
        assert isinstance(
            fix,
            DeleteLeafRequest
            | DeleteNoteCarrierRequest
            | DeleteRhythmicGroupRequest
            | DeleteTemporalAnchorRequest,
        )
        targets.append(fix.target)
    assert targets.count(empty) == 1
    assert bare in targets
    assert emptied.carrier in targets
    assert orphan in targets
    assert len(targets) == 4
    assert of_rests not in targets


# --- the anchor analyzer --------------------------------------------------------------


@pytest.mark.unit
def test_the_anchor_analyzer_refuses_a_second_anchor_at_one_position() -> None:
    score: Score = build_score(bars=1)
    anchor_at(score=score, at=_Q)

    with pytest.raises(MutationRejectedError, match="Anchor already exists"):
        _process(
            score=score,
            requests=[
                CreateTemporalAnchorRequest(
                    measure=score.measures[0],
                    position=MeasurePosition.of_fraction(fraction=_Q),
                    out=ResultRef[TemporalAnchor](),
                )
            ],
        )


# --- one gesture, one journal ---------------------------------------------------------


@pytest.mark.unit
def test_rolling_back_a_displacing_gesture_restores_the_group() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0, beats=(0,))
    eighth_triplet(score=score, parent=score.voice, at=_Q)
    quarters(score=score, bar=0, beats=(2, 3))
    before = layout(score=score)

    log: MutationLog = _create_note(score=score, at=_Q, rhythmic_value=RhythmicValue.HALF)
    log.rollback()

    assert layout(score=score) == before
    assert len(score.measures[0].anchors) == 6
