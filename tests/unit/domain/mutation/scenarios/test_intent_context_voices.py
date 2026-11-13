import pytest
from tests.unit.domain.document_builders import score

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import Context, DynamicChange, Hairpin, Slur
from piano_app.domain.score.document.models.notation import DynamicMarking
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import (
    AddContextVoiceIntent,
    CreateHairpinIntent,
    CreateSlurIntent,
    EditIntent,
    RemoveContextVoiceIntent,
    SetDynamicIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError

_START: MeasurePosition = MeasurePosition.of(numerator=0, denominator=1)


def _run(*, document: ScoreDocument, intent: EditIntent) -> MutationLog:
    return build_engine().process(
        document=document,
        requests=build_compiler().compile(document=document, intent=intent),
    )


def _all[T: Context](*, document: ScoreDocument, kind: type[T]) -> list[T]:
    """Every context of exactly this kind, in the order of the timeline."""
    return [
        context
        for measure in document.measures
        for anchor in measure.anchors
        for context in anchor.starting_contexts
        if type(context) is kind
    ]


def _slur(*, document: ScoreDocument, voice: int) -> None:
    _run(
        document=document,
        intent=CreateSlurIntent(
            start_measure_id=document.measures[0].id,
            start_position=_START,
            end_measure_id=document.measures[1].id,
            end_position=_START,
            voice_ids=(document.voices[voice].id,),
        ),
    )


def _hairpin(*, document: ScoreDocument, voice: int) -> None:
    _run(
        document=document,
        intent=CreateHairpinIntent(
            start_measure_id=document.measures[0].id,
            start_position=_START,
            end_measure_id=document.measures[1].id,
            end_position=_START,
            voice_ids=(document.voices[voice].id,),
            target=DynamicMarking.FORTE,
        ),
    )


def _dynamic(*, document: ScoreDocument, voice: int, dynamic: DynamicMarking) -> None:
    _run(
        document=document,
        intent=SetDynamicIntent(
            measure_id=document.measures[1].id,
            position=_START,
            voice_ids=(document.voices[voice].id,),
            dynamic=dynamic,
        ),
    )


def test_a_voice_added_to_a_context_joins_it_and_leaves_with_an_undo() -> None:
    document: ScoreDocument = score()
    _slur(document=document, voice=0)
    (slur,) = _all(document=document, kind=Slur)

    log: MutationLog = _run(
        document=document,
        intent=AddContextVoiceIntent(context_id=slur.id, voice_id=document.voices[1].id),
    )

    assert slur.voices == list(document.voices)
    assert slur in document.voices[1].contexts

    log.rollback()
    assert slur.voices == [document.voices[0]]
    assert slur not in document.voices[1].contexts


def test_a_voice_already_in_a_context_cannot_be_added_again() -> None:
    document: ScoreDocument = score()
    _slur(document=document, voice=0)
    (slur,) = _all(document=document, kind=Slur)

    with pytest.raises(MutationRejectedError, match="already belongs"):
        _run(
            document=document,
            intent=AddContextVoiceIntent(context_id=slur.id, voice_id=document.voices[0].id),
        )


def test_a_voice_cannot_be_added_where_it_already_has_a_context_of_that_kind_at_that_place() -> (
    None
):
    document: ScoreDocument = score()
    _dynamic(document=document, voice=0, dynamic=DynamicMarking.FORTE)
    _dynamic(document=document, voice=1, dynamic=DynamicMarking.PIANO)
    forte: DynamicChange = next(
        dynamic
        for dynamic in _all(document=document, kind=DynamicChange)
        if dynamic.voices == [document.voices[0]] and dynamic.start.measure is document.measures[1]
    )

    with pytest.raises(MutationRejectedError, match="already starts there"):
        _run(
            document=document,
            intent=AddContextVoiceIntent(context_id=forte.id, voice_id=document.voices[1].id),
        )

    assert forte.voices == [document.voices[0]]


def test_a_voice_cannot_be_added_to_a_hairpin_over_another_hairpin_of_that_voice() -> None:
    document: ScoreDocument = score()
    _hairpin(document=document, voice=0)
    _hairpin(document=document, voice=1)
    first: Hairpin = _all(document=document, kind=Hairpin)[0]

    with pytest.raises(MutationRejectedError, match="cannot overlap"):
        _run(
            document=document,
            intent=AddContextVoiceIntent(context_id=first.id, voice_id=document.voices[1].id),
        )


def test_slurs_may_overlap_so_a_voice_with_a_slur_can_join_another() -> None:
    document: ScoreDocument = score()
    _slur(document=document, voice=0)
    _slur(document=document, voice=1)
    first: Slur = _all(document=document, kind=Slur)[0]

    _run(
        document=document,
        intent=AddContextVoiceIntent(context_id=first.id, voice_id=document.voices[1].id),
    )

    assert first.voices == list(document.voices)


def test_a_voice_removed_from_a_context_leaves_the_context_and_its_other_voices() -> None:
    document: ScoreDocument = score()
    _slur(document=document, voice=0)
    (slur,) = _all(document=document, kind=Slur)
    _run(
        document=document,
        intent=AddContextVoiceIntent(context_id=slur.id, voice_id=document.voices[1].id),
    )

    log: MutationLog = _run(
        document=document,
        intent=RemoveContextVoiceIntent(context_id=slur.id, voice_id=document.voices[0].id),
    )

    assert slur.voices == [document.voices[1]]
    assert slur not in document.voices[0].contexts

    log.rollback()
    assert slur.voices == list(document.voices)


def test_the_last_voice_of_a_context_cannot_be_removed_nor_one_that_is_not_in_it() -> None:
    document: ScoreDocument = score()
    _slur(document=document, voice=0)
    (slur,) = _all(document=document, kind=Slur)

    with pytest.raises(MutationRejectedError, match="at least one voice"):
        _run(
            document=document,
            intent=RemoveContextVoiceIntent(context_id=slur.id, voice_id=document.voices[0].id),
        )

    with pytest.raises(MutationRejectedError, match="does not belong"):
        _run(
            document=document,
            intent=RemoveContextVoiceIntent(context_id=slur.id, voice_id=document.voices[1].id),
        )
