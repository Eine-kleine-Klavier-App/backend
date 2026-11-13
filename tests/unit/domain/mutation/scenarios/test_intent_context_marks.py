from fractions import Fraction

import pytest
from tests.unit.domain.document_builders import note, score

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import (
    ClefChange,
    Context,
    DynamicChange,
    KeySignatureChange,
    Slur,
    SpanContext,
)
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import Accidental, Clef, DynamicMarking
from piano_app.domain.score.document.models.structural import MeasurePosition
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import (
    DeleteClefIntent,
    EditIntent,
    MoveContextEndIntent,
    MoveContextStartIntent,
    PitchEditMode,
    RemoveContextVoiceIntent,
    SetClefIntent,
    SetDynamicIntent,
    SetKeySignatureIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateSlurRequest,
)
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch

_START: MeasurePosition = MeasurePosition.of(numerator=0, denominator=1)
_BEAT_TWO: MeasurePosition = MeasurePosition.of(numerator=1, denominator=4)
_NATURALS: tuple[Accidental, ...] = (Accidental.NATURAL,) * 7
_ONE_SHARP: tuple[Accidental, ...] = (
    *(Accidental.NATURAL,) * 3,
    Accidental.SHARP,
    *(Accidental.NATURAL,) * 3,
)


def _run(*, document: ScoreDocument, intent: EditIntent) -> MutationLog:
    return build_engine().process(
        document=document,
        requests=build_compiler().compile(document=document, intent=intent),
    )


def _midi(*, document: ScoreDocument, target: Note) -> int:
    """What a note sounds like, read from a fresh index."""
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    pitch: ScorePitch = ScorePitch(
        document=document,
        geometry=geometry,
        contexts=ContextIndex(document=document, geometry=geometry),
    )
    return pitch.pitch_of(note=target).midi_note


def _contexts[T: Context](*, document: ScoreDocument, kind: type[T]) -> list[T]:
    """Every context of exactly this kind, in the order of the timeline."""
    return [
        context
        for measure in document.measures
        for anchor in measure.anchors
        for context in anchor.starting_contexts
        if type(context) is kind
    ]


def _place(*, document: ScoreDocument, context: Context) -> tuple[int, Fraction]:
    """The measure index and the position where a context starts."""
    return document.measures.index(context.start.measure), context.start.position.value


def _clef_at(*, document: ScoreDocument, measure: int) -> ClefChange:
    """The clef of the first staff that starts a measure."""
    (clef,) = [
        clef
        for clef in _contexts(document=document, kind=ClefChange)
        if clef.staff is document.staffs[0]
        and _place(document=document, context=clef) == (measure, 0)
    ]

    return clef


def _set_clef(
    *, document: ScoreDocument, measure: int, clef: Clef, mode: PitchEditMode
) -> SetClefIntent:
    return SetClefIntent(
        staff_id=document.staffs[0].id,
        measure_id=document.measures[measure].id,
        position=_START,
        clef=clef,
        octave_transposition=0,
        mode=mode,
    )


def test_a_clef_set_keeping_the_steps_leaves_the_notes_on_their_steps_and_changes_their_sound() -> (
    None
):
    document: ScoreDocument = score()
    before: Note = note(document, Fraction(1, 4), step=-2)
    after: Note = note(document, Fraction(1), step=-2)
    sounded_before: int = _midi(document=document, target=before)
    sounded_after: int = _midi(document=document, target=after)

    _run(
        document=document,
        intent=_set_clef(
            document=document, measure=1, clef=Clef.BASS, mode=PitchEditMode.PRESERVE_STEP
        ),
    )

    assert [clef.clef for clef in _contexts(document=document, kind=ClefChange)] == [
        Clef.TREBLE,
        Clef.BASS,
        Clef.BASS,
    ]
    assert (before.staff_step, after.staff_step) == (-2, -2)
    assert _midi(document=document, target=before) == sounded_before
    assert _midi(document=document, target=after) != sounded_after


def test_a_clef_set_keeping_the_pitch_moves_the_notes_after_it_to_steps_that_sound_as_before() -> (
    None
):
    document: ScoreDocument = score()
    after: Note = note(document, Fraction(1), step=-2)
    sounded: int = _midi(document=document, target=after)

    _run(
        document=document,
        intent=_set_clef(
            document=document, measure=1, clef=Clef.BASS, mode=PitchEditMode.PRESERVE_PITCH
        ),
    )

    assert after.staff_step != -2
    assert _midi(document=document, target=after) == sounded


def test_a_second_clef_set_at_the_same_place_replaces_the_first() -> None:
    document: ScoreDocument = score()
    _run(
        document=document,
        intent=_set_clef(
            document=document, measure=1, clef=Clef.BASS, mode=PitchEditMode.PRESERVE_STEP
        ),
    )

    _run(
        document=document,
        intent=_set_clef(
            document=document, measure=1, clef=Clef.TREBLE, mode=PitchEditMode.PRESERVE_STEP
        ),
    )

    here: list[ClefChange] = [
        clef
        for clef in _contexts(document=document, kind=ClefChange)
        if clef.staff is document.staffs[0] and _place(document=document, context=clef) == (1, 0)
    ]
    assert [clef.clef for clef in here] == [Clef.TREBLE]


def test_a_key_signature_is_set_at_its_place_and_a_second_one_there_replaces_it() -> None:
    document: ScoreDocument = score()
    staff_id: str = document.staffs[0].id
    measure_id: str = document.measures[1].id

    _run(
        document=document,
        intent=SetKeySignatureIntent(
            staff_id=staff_id, measure_id=measure_id, position=_START, alterations=_ONE_SHARP
        ),
    )
    placed: list[KeySignatureChange] = [
        key
        for key in _contexts(document=document, kind=KeySignatureChange)
        if _place(document=document, context=key) == (1, 0)
    ]
    assert [key.alterations for key in placed] == [_ONE_SHARP]

    _run(
        document=document,
        intent=SetKeySignatureIntent(
            staff_id=staff_id, measure_id=measure_id, position=_START, alterations=_NATURALS
        ),
    )
    replaced: list[KeySignatureChange] = [
        key
        for key in _contexts(document=document, kind=KeySignatureChange)
        if _place(document=document, context=key) == (1, 0)
    ]
    assert [key.alterations for key in replaced] == [_NATURALS]


def test_a_key_signature_that_does_not_give_seven_alterations_is_refused() -> None:
    document: ScoreDocument = score()

    with pytest.raises(MutationRejectedError, match="alterations"):
        _run(
            document=document,
            intent=SetKeySignatureIntent(
                staff_id=document.staffs[0].id,
                measure_id=document.measures[1].id,
                position=_START,
                alterations=_ONE_SHARP[:6],
            ),
        )

    assert len(_contexts(document=document, kind=KeySignatureChange)) == 2


def test_a_key_signature_with_a_double_accidental_is_refused() -> None:
    document: ScoreDocument = score()

    with pytest.raises(MutationRejectedError, match="no double accidentals"):
        _run(
            document=document,
            intent=SetKeySignatureIntent(
                staff_id=document.staffs[0].id,
                measure_id=document.measures[1].id,
                position=_START,
                alterations=(Accidental.DOUBLE_SHARP, *_NATURALS[1:]),
            ),
        )

    assert len(_contexts(document=document, kind=KeySignatureChange)) == 2


def test_a_clef_taken_out_of_a_measure_returns_at_the_start_of_the_next_one() -> None:
    document: ScoreDocument = score()
    _run(
        document=document,
        intent=_set_clef(
            document=document, measure=1, clef=Clef.BASS, mode=PitchEditMode.PRESERVE_STEP
        ),
    )
    clef: ClefChange = _clef_at(document=document, measure=1)
    assert _place(document=document, context=clef) == (1, 0)

    log: MutationLog = _run(
        document=document,
        intent=DeleteClefIntent(
            clef_id=clef.id,
            measure_ids=(document.measures[1].id,),
            mode=PitchEditMode.PRESERVE_STEP,
        ),
    )

    assert _place(document=document, context=clef) == (2, 0)

    log.rollback()
    assert _place(document=document, context=clef) == (1, 0)


def test_a_clef_taken_out_of_the_last_measure_is_deleted() -> None:
    document: ScoreDocument = score()
    _run(
        document=document,
        intent=_set_clef(
            document=document, measure=2, clef=Clef.BASS, mode=PitchEditMode.PRESERVE_STEP
        ),
    )
    clef: ClefChange = _clef_at(document=document, measure=2)

    _run(
        document=document,
        intent=DeleteClefIntent(
            clef_id=clef.id,
            measure_ids=(),
            mode=PitchEditMode.PRESERVE_STEP,
        ),
    )

    assert clef not in _contexts(document=document, kind=ClefChange)


def test_the_clef_at_the_start_of_the_score_cannot_be_taken_out() -> None:
    document: ScoreDocument = score()
    initial: ClefChange = _clef_at(document=document, measure=0)

    with pytest.raises(MutationRejectedError, match="cannot be deleted or moved"):
        _run(
            document=document,
            intent=DeleteClefIntent(
                clef_id=initial.id, measure_ids=(), mode=PitchEditMode.PRESERVE_STEP
            ),
        )

    assert initial in _contexts(document=document, kind=ClefChange)


def test_a_dynamic_set_for_one_voice_leaves_the_other_voices_alone() -> None:
    document: ScoreDocument = score()

    _run(
        document=document,
        intent=SetDynamicIntent(
            measure_id=document.measures[1].id,
            position=_START,
            voice_ids=(document.voices[0].id,),
            dynamic=DynamicMarking.FORTE,
        ),
    )

    set_here: list[DynamicChange] = [
        dynamic
        for dynamic in _contexts(document=document, kind=DynamicChange)
        if _place(document=document, context=dynamic) == (1, 0)
    ]
    assert [(dynamic.dynamic, dynamic.voices) for dynamic in set_here] == [
        (DynamicMarking.FORTE, [document.voices[0]])
    ]
    # the dynamic every voice starts with, and the new one
    assert len(_contexts(document=document, kind=DynamicChange)) == 2


def test_a_dynamic_set_over_one_sharing_a_voice_takes_that_voice_from_it() -> None:
    document: ScoreDocument = score()
    both: tuple[str, ...] = tuple(voice.id for voice in document.voices)
    _run(
        document=document,
        intent=SetDynamicIntent(
            measure_id=document.measures[1].id,
            position=_START,
            voice_ids=both,
            dynamic=DynamicMarking.FORTE,
        ),
    )

    _run(
        document=document,
        intent=SetDynamicIntent(
            measure_id=document.measures[1].id,
            position=_START,
            voice_ids=(document.voices[0].id,),
            dynamic=DynamicMarking.PIANO,
        ),
    )

    set_here: list[DynamicChange] = [
        dynamic
        for dynamic in _contexts(document=document, kind=DynamicChange)
        if _place(document=document, context=dynamic) == (1, 0)
    ]
    assert sorted((dynamic.dynamic.value, len(dynamic.voices)) for dynamic in set_here) == [
        ("f", 1),
        ("p", 1),
    ]
    owners: dict[str, list[int]] = {
        dynamic.dynamic.value: [document.voices.index(voice) for voice in dynamic.voices]
        for dynamic in set_here
    }
    assert owners == {"f": [1], "p": [0]}


def test_a_voice_removed_from_a_dynamic_leaves_the_dynamic_and_its_other_voices() -> None:
    document: ScoreDocument = score()
    _run(
        document=document,
        intent=SetDynamicIntent(
            measure_id=document.measures[1].id,
            position=_START,
            voice_ids=tuple(voice.id for voice in document.voices),
            dynamic=DynamicMarking.FORTE,
        ),
    )
    shared: DynamicChange = _contexts(document=document, kind=DynamicChange)[1]

    log: MutationLog = _run(
        document=document,
        intent=RemoveContextVoiceIntent(context_id=shared.id, voice_id=document.voices[0].id),
    )

    assert shared.voices == [document.voices[1]]

    log.rollback()
    assert shared.voices == list(document.voices)


def test_a_voice_cannot_be_removed_from_a_dynamic_in_the_ways_that_would_lose_one() -> None:
    document: ScoreDocument = score()
    _run(
        document=document,
        intent=SetDynamicIntent(
            measure_id=document.measures[1].id,
            position=_START,
            voice_ids=(document.voices[1].id,),
            dynamic=DynamicMarking.FORTE,
        ),
    )
    only_second: DynamicChange = _contexts(document=document, kind=DynamicChange)[1]
    assert only_second.voices == [document.voices[1]]

    with pytest.raises(MutationRejectedError, match="does not belong"):
        _run(
            document=document,
            intent=RemoveContextVoiceIntent(
                context_id=only_second.id, voice_id=document.voices[0].id
            ),
        )

    with pytest.raises(MutationRejectedError, match="at least one voice"):
        _run(
            document=document,
            intent=RemoveContextVoiceIntent(
                context_id=only_second.id, voice_id=document.voices[1].id
            ),
        )

    _run(
        document=document,
        intent=SetDynamicIntent(
            measure_id=document.measures[0].id,
            position=_START,
            voice_ids=tuple(voice.id for voice in document.voices),
            dynamic=DynamicMarking.FORTE,
        ),
    )
    shared_at_start: DynamicChange = _contexts(document=document, kind=DynamicChange)[0]
    assert shared_at_start.voices == list(document.voices)

    with pytest.raises(MutationRejectedError, match="start of the score"):
        _run(
            document=document,
            intent=RemoveContextVoiceIntent(
                context_id=shared_at_start.id, voice_id=document.voices[0].id
            ),
        )


def test_a_clef_moved_keeping_the_pitch_keeps_what_the_notes_after_it_sound_like() -> None:
    document: ScoreDocument = score()
    _run(
        document=document,
        intent=_set_clef(
            document=document, measure=1, clef=Clef.BASS, mode=PitchEditMode.PRESERVE_STEP
        ),
    )
    clef: ClefChange = _clef_at(document=document, measure=1)
    moved: Note = note(document, Fraction(1) + Fraction(1, 4), step=-2)
    sounded: int = _midi(document=document, target=moved)

    _run(
        document=document,
        intent=MoveContextStartIntent(
            context_id=clef.id,
            measure_id=document.measures[1].id,
            position=_BEAT_TWO,
            mode=PitchEditMode.PRESERVE_PITCH,
        ),
    )

    assert _place(document=document, context=clef) == (1, Fraction(1, 4))
    assert _midi(document=document, target=moved) == sounded


def test_the_context_at_the_start_of_the_score_cannot_be_moved() -> None:
    document: ScoreDocument = score()
    initial: ClefChange = _clef_at(document=document, measure=0)

    with pytest.raises(MutationRejectedError, match="cannot be deleted or moved"):
        _run(
            document=document,
            intent=MoveContextStartIntent(
                context_id=initial.id,
                measure_id=document.measures[1].id,
                position=_START,
                mode=PitchEditMode.PRESERVE_STEP,
            ),
        )

    assert _place(document=document, context=initial) == (0, 0)


def _slur(*, document: ScoreDocument) -> Slur:
    build_engine().process(
        document=document,
        requests=[
            CreateSlurRequest(
                start_measure=document.measures[1],
                start_position=_START,
                end_measure=document.measures[1],
                end_position=_BEAT_TWO,
                voices=(document.voices[0],),
            )
        ],
    )
    (slur,) = _contexts(document=document, kind=Slur)

    return slur


def test_the_end_of_a_span_is_moved_to_the_new_place() -> None:
    document: ScoreDocument = score()
    slur: Slur = _slur(document=document)

    log: MutationLog = _run(
        document=document,
        intent=MoveContextEndIntent(
            context_id=slur.id,
            measure_id=document.measures[2].id,
            position=_START,
            mode=PitchEditMode.PRESERVE_STEP,
        ),
    )

    assert (document.measures.index(slur.end.measure), slur.end.position.value) == (2, 0)

    log.rollback()
    assert (document.measures.index(slur.end.measure), slur.end.position.value) == (
        1,
        Fraction(1, 4),
    )


def test_the_end_of_a_span_cannot_be_moved_to_where_it_starts_or_before() -> None:
    document: ScoreDocument = score()
    slur: Slur = _slur(document=document)
    assert isinstance(slur, SpanContext)

    with pytest.raises(MutationRejectedError, match="end must stay after its start"):
        _run(
            document=document,
            intent=MoveContextEndIntent(
                context_id=slur.id,
                measure_id=document.measures[1].id,
                position=_START,
                mode=PitchEditMode.PRESERVE_STEP,
            ),
        )

    assert (document.measures.index(slur.end.measure), slur.end.position.value) == (
        1,
        Fraction(1, 4),
    )
