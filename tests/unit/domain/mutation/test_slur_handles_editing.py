from fractions import Fraction

import pytest
from tests.unit.domain.document_builders import note, score

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import Context, Hairpin, Slur
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import DynamicMarking
from piano_app.domain.score.document.models.presentation import (
    EndpointOffsets,
    HorizontalEndpointOffsets,
    HorizontalOffset,
    PresentationTarget,
    ReferencePoint,
    VerticalOffset,
)
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import (
    CreateHairpinIntent,
    CreateSlurIntent,
    DeleteBatchIntent,
    EditIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.presentation import (
    PresentationEditor,
    SetEndpointOffsets,
    SetHorizontalEndpointOffsets,
    SetHorizontalOffset,
    SetVerticalOffset,
)
from piano_app.domain.score.document.services.presentation.capabilities import (
    presentation_capabilities,
)

# The six handles of a slur are the presentation system's own capabilities on two reference points
# of the slur: the body (the top edge: the whole slur up and down, the heights of its two ends) and
# the lower edge (three handles: the middle and the two corners, each up and down and sideways).

_START: MeasurePosition = MeasurePosition.of(numerator=0, denominator=1)


def _run(*, document: ScoreDocument, intent: EditIntent) -> MutationLog:
    return build_engine().process(
        document=document,
        requests=build_compiler().compile(document=document, intent=intent),
    )


def _context[T: Context](*, document: ScoreDocument, kind: type[T]) -> T:
    (found,) = (
        context
        for measure in document.measures
        for anchor in measure.anchors
        for context in anchor.starting_contexts
        if type(context) is kind
    )

    return found


def _with_a_slur_and_a_hairpin() -> tuple[ScoreDocument, Slur, Hairpin, Note]:
    document: ScoreDocument = score()
    notes: list[Note] = [note(document, Fraction(1) + Fraction(beat, 4)) for beat in range(4)]
    end: MeasurePosition = MeasurePosition.of(numerator=3, denominator=4)
    _run(
        document=document,
        intent=CreateSlurIntent(
            start_measure_id=document.measures[1].id,
            start_position=_START,
            end_measure_id=document.measures[1].id,
            end_position=end,
            voice_ids=(document.voices[0].id,),
        ),
    )
    _run(
        document=document,
        intent=CreateHairpinIntent(
            start_measure_id=document.measures[1].id,
            start_position=_START,
            end_measure_id=document.measures[1].id,
            end_position=end,
            voice_ids=(document.voices[0].id,),
            target=DynamicMarking.FORTE,
        ),
    )

    return (
        document,
        _context(document=document, kind=Slur),
        _context(document=document, kind=Hairpin),
        notes[0],
    )


def _top(slur: Slur) -> PresentationTarget:
    return PresentationTarget(entity_id=slur.id)


def _lower(slur: Slur) -> PresentationTarget:
    return PresentationTarget(entity_id=slur.id, reference=ReferencePoint.LOWER_EDGE)


@pytest.mark.unit
def test_a_slur_has_the_top_edge_and_the_lower_edge_to_shape() -> None:
    document, slur, hairpin, _note = _with_a_slur_and_a_hairpin()

    capabilities = presentation_capabilities(document=document)

    top = capabilities[_top(slur)]
    lower = capabilities[_lower(slur)]
    assert (top.vertical, top.endpoints, top.horizontal, top.horizontal_endpoints) == (
        True,
        True,
        False,
        False,
    )
    assert (lower.vertical, lower.endpoints, lower.horizontal, lower.horizontal_endpoints) == (
        True,
        True,
        True,
        True,
    )
    of_hairpin = capabilities[PresentationTarget(entity_id=hairpin.id)]
    assert (of_hairpin.vertical, of_hairpin.endpoints) == (True, False)
    assert PresentationTarget(entity_id=hairpin.id, reference=ReferencePoint.LOWER_EDGE) not in (
        capabilities
    )


@pytest.mark.unit
def test_the_six_handles_of_a_slur_are_set_and_reset() -> None:
    document, slur, _hairpin, _note = _with_a_slur_and_a_hairpin()
    log: MutationLog = MutationLog()

    PresentationEditor().apply(
        document=document,
        commands=[
            SetVerticalOffset(target=_top(slur), value=VerticalOffset(value=-1)),
            SetEndpointOffsets(target=_top(slur), value=EndpointOffsets(left=0.5, right=-0.5)),
            SetVerticalOffset(target=_lower(slur), value=VerticalOffset(value=1)),
            SetEndpointOffsets(target=_lower(slur), value=EndpointOffsets(left=0.25, right=0.5)),
            SetHorizontalOffset(target=_lower(slur), value=HorizontalOffset(value=-0.5)),
            SetHorizontalEndpointOffsets(
                target=_lower(slur), value=HorizontalEndpointOffsets(left=0.5, right=-0.5)
            ),
        ],
        sink=log,
    )

    presentation = document.presentation
    assert presentation.vertical[_top(slur)] == VerticalOffset(value=-1)
    assert presentation.endpoints[_top(slur)] == EndpointOffsets(left=0.5, right=-0.5)
    assert presentation.vertical[_lower(slur)] == VerticalOffset(value=1)
    assert presentation.endpoints[_lower(slur)] == EndpointOffsets(left=0.25, right=0.5)
    assert presentation.horizontal[_lower(slur)] == HorizontalOffset(value=-0.5)
    assert presentation.horizontal_endpoints[_lower(slur)] == HorizontalEndpointOffsets(
        left=0.5, right=-0.5
    )

    PresentationEditor().apply(
        document=document,
        commands=[
            SetHorizontalOffset(target=_lower(slur), value=None),
            SetHorizontalEndpointOffsets(target=_lower(slur), value=None),
        ],
        sink=MutationLog(),
    )
    assert not presentation.horizontal and not presentation.horizontal_endpoints
    assert _lower(slur) in presentation.vertical

    log.rollback()
    assert not presentation.vertical and not presentation.endpoints


@pytest.mark.unit
def test_a_sideways_move_is_refused_where_there_is_no_such_handle_and_nothing_changes() -> None:
    document, slur, hairpin, first = _with_a_slur_and_a_hairpin()
    log: MutationLog = MutationLog()
    refused: list[PresentationTarget] = [
        _top(slur),  # the top edge of a slur moves up and down only
        PresentationTarget(entity_id=hairpin.id),
        PresentationTarget(entity_id=first.note_carrier.id),
    ]

    for target in refused:
        with pytest.raises(ValueError, match="capability is unavailable"):
            PresentationEditor().apply(
                document=document,
                commands=[
                    SetHorizontalOffset(target=_lower(slur), value=HorizontalOffset(value=1)),
                    SetHorizontalOffset(target=target, value=HorizontalOffset(value=1)),
                ],
                sink=log,
            )

    assert not log.has_changes and not document.presentation.horizontal


@pytest.mark.unit
def test_the_handles_of_a_slur_that_is_deleted_are_dropped() -> None:
    document, slur, _hairpin, _note = _with_a_slur_and_a_hairpin()
    PresentationEditor().apply(
        document=document,
        commands=[
            SetVerticalOffset(target=_top(slur), value=VerticalOffset(value=1)),
            SetHorizontalOffset(target=_lower(slur), value=HorizontalOffset(value=1)),
            SetHorizontalEndpointOffsets(
                target=_lower(slur), value=HorizontalEndpointOffsets(left=1)
            ),
        ],
        sink=MutationLog(),
    )

    _run(document=document, intent=DeleteBatchIntent(entity_ids=(slur.id,)))
    PresentationEditor().prune(document=document, sink=MutationLog())

    presentation = document.presentation
    assert not presentation.vertical and not presentation.horizontal
    assert not presentation.horizontal_endpoints


@pytest.mark.unit
@pytest.mark.parametrize("value", [0, -0.5])
def test_a_factor_of_the_automatic_size_must_be_above_zero(value: float) -> None:
    document, slur, hairpin, _note = _with_a_slur_and_a_hairpin()
    height = PresentationTarget(entity_id=slur.id, reference=ReferencePoint.HEIGHT)

    for target in (height, PresentationTarget(entity_id=hairpin.id)):
        with pytest.raises(ValueError, match="factor above zero"):
            PresentationEditor().apply(
                document=document,
                commands=[SetVerticalOffset(target=target, value=VerticalOffset(value=value))],
                sink=MutationLog(),
            )

    assert not document.presentation.vertical


@pytest.mark.unit
def test_a_place_in_the_frame_of_a_slur_may_lie_anywhere_across_it() -> None:
    document, slur, _hairpin, _note = _with_a_slur_and_a_hairpin()

    PresentationEditor().apply(
        document=document,
        commands=[
            SetVerticalOffset(target=_top(slur), value=VerticalOffset(value=-0.25)),
            SetHorizontalOffset(target=_lower(slur), value=HorizontalOffset(value=0.6)),
        ],
        sink=MutationLog(),
    )

    assert document.presentation.vertical[_top(slur)].value == -0.25
    assert document.presentation.horizontal[_lower(slur)].value == 0.6
