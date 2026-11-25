from fractions import Fraction

import pytest
from tests.unit.domain.document_builders import note, score

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import (
    Context,
    Hairpin,
    OctaveTransposition,
    Slur,
    SustainHold,
    TempoTransition,
)
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.notation import DynamicMarking
from piano_app.domain.score.document.models.structural import MeasurePosition, Voice
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import (
    CreateHairpinIntent,
    CreateOctaveTranspositionIntent,
    CreateSlurIntent,
    CreateSustainHoldIntent,
    CreateTempoTransitionIntent,
    DeleteBatchIntent,
    DeleteOctaveTranspositionIntent,
    EditIntent,
    MoveContextEndIntent,
    MoveContextStartIntent,
    PitchEditMode,
    SetDynamicIntent,
    SetHairpinTargetIntent,
    SetTempoTransitionTargetIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch

_START: MeasurePosition = MeasurePosition.of(numerator=0, denominator=1)
_BEAT_TWO: MeasurePosition = MeasurePosition.of(numerator=1, denominator=4)
# what a score starts with: a dynamic of p on every voice, a tempo of 90 quarters a minute
_INITIAL_DYNAMIC: DynamicMarking = DynamicMarking.PIANO
_INITIAL_BPM: int = 90


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


def _hairpin(*, document: ScoreDocument, target: DynamicMarking) -> CreateHairpinIntent:
    """A hairpin of the first voice from the second measure to the third."""
    return CreateHairpinIntent(
        start_measure_id=document.measures[1].id,
        start_position=_START,
        end_measure_id=document.measures[2].id,
        end_position=_START,
        voice_ids=(document.voices[0].id,),
        target=target,
    )


def _transition(*, document: ScoreDocument, target_bpm: int) -> CreateTempoTransitionIntent:
    """A tempo transition from the second measure to the third."""
    return CreateTempoTransitionIntent(
        start_measure_id=document.measures[1].id,
        start_position=_START,
        end_measure_id=document.measures[2].id,
        end_position=_START,
        target_bpm=target_bpm,
    )


def _octave(
    *, document: ScoreDocument, start: MeasurePosition, mode: PitchEditMode
) -> CreateOctaveTranspositionIntent:
    """An octave line up on the first staff from the second measure to the third."""
    return CreateOctaveTranspositionIntent(
        staff_id=document.staffs[0].id,
        start_measure_id=document.measures[1].id,
        start_position=start,
        end_measure_id=document.measures[2].id,
        end_position=_START,
        octaves=1,
        mode=mode,
    )


def test_a_hairpin_to_a_target_dynamic_climbs_as_many_levels_as_lie_between() -> None:
    document: ScoreDocument = score()

    log: MutationLog = _run(
        document=document, intent=_hairpin(document=document, target=DynamicMarking.FORTE)
    )

    (hairpin,) = _contexts(document=document, kind=Hairpin)
    assert hairpin.steps == DynamicMarking.FORTE.level - _INITIAL_DYNAMIC.level
    assert hairpin.voice is document.voices[0]
    assert document.measures.index(hairpin.start.measure) == 1
    assert document.measures.index(hairpin.end.measure) == 2

    log.rollback()
    assert _contexts(document=document, kind=Hairpin) == []


def test_a_hairpin_for_voices_that_start_at_different_dynamics_climbs_from_each_start() -> None:
    document: ScoreDocument = score()
    first, second = document.voices
    _run(
        document=document,
        intent=SetDynamicIntent(
            measure_id=document.measures[1].id,
            position=_START,
            voice_ids=(first.id,),
            dynamic=DynamicMarking.FORTE,
        ),
    )

    log: MutationLog = _run(
        document=document,
        intent=CreateHairpinIntent(
            start_measure_id=document.measures[1].id,
            start_position=_START,
            end_measure_id=document.measures[2].id,
            end_position=_START,
            voice_ids=(first.id, second.id),
            target=DynamicMarking.FORTISSIMO,
        ),
    )

    hairpins: dict[Voice, Hairpin] = {
        hairpin.voice: hairpin for hairpin in _contexts(document=document, kind=Hairpin)
    }
    assert hairpins[first].steps == DynamicMarking.FORTISSIMO.level - DynamicMarking.FORTE.level
    assert hairpins[second].steps == DynamicMarking.FORTISSIMO.level - _INITIAL_DYNAMIC.level

    log.rollback()
    assert _contexts(document=document, kind=Hairpin) == []


def test_a_hairpin_that_would_change_nothing_for_one_voice_is_refused_for_all() -> None:
    document: ScoreDocument = score()
    first, second = document.voices
    _run(
        document=document,
        intent=SetDynamicIntent(
            measure_id=document.measures[1].id,
            position=_START,
            voice_ids=(first.id,),
            dynamic=DynamicMarking.FORTE,
        ),
    )

    with pytest.raises(MutationRejectedError, match="must change the dynamic"):
        _run(
            document=document,
            intent=CreateHairpinIntent(
                start_measure_id=document.measures[1].id,
                start_position=_START,
                end_measure_id=document.measures[2].id,
                end_position=_START,
                voice_ids=(first.id, second.id),
                target=DynamicMarking.FORTE,
            ),
        )

    assert _contexts(document=document, kind=Hairpin) == []


def test_a_hairpin_to_the_dynamic_it_starts_at_is_refused() -> None:
    document: ScoreDocument = score()

    with pytest.raises(MutationRejectedError, match="must change the dynamic"):
        _run(document=document, intent=_hairpin(document=document, target=_INITIAL_DYNAMIC))

    assert _contexts(document=document, kind=Hairpin) == []


def test_a_new_target_of_a_hairpin_changes_the_levels_it_climbs() -> None:
    document: ScoreDocument = score()
    _run(document=document, intent=_hairpin(document=document, target=DynamicMarking.FORTE))
    (hairpin,) = _contexts(document=document, kind=Hairpin)

    log: MutationLog = _run(
        document=document,
        intent=SetHairpinTargetIntent(hairpin_ids=(hairpin.id,), target=DynamicMarking.MEZZO_FORTE),
    )

    assert hairpin.steps == DynamicMarking.MEZZO_FORTE.level - _INITIAL_DYNAMIC.level

    log.rollback()
    assert hairpin.steps == DynamicMarking.FORTE.level - _INITIAL_DYNAMIC.level


def test_a_new_target_of_a_hairpin_at_the_dynamic_it_starts_at_is_refused() -> None:
    document: ScoreDocument = score()
    _run(document=document, intent=_hairpin(document=document, target=DynamicMarking.FORTE))
    (hairpin,) = _contexts(document=document, kind=Hairpin)
    steps: int = hairpin.steps

    with pytest.raises(MutationRejectedError, match="must change the dynamic"):
        _run(
            document=document,
            intent=SetHairpinTargetIntent(hairpin_ids=(hairpin.id,), target=_INITIAL_DYNAMIC),
        )

    assert hairpin.steps == steps


def test_a_slur_is_put_over_each_voice_it_names() -> None:
    document: ScoreDocument = score()

    log: MutationLog = _run(
        document=document,
        intent=CreateSlurIntent(
            start_measure_id=document.measures[1].id,
            start_position=_START,
            end_measure_id=document.measures[2].id,
            end_position=_START,
            voice_ids=tuple(voice.id for voice in document.voices),
        ),
    )

    slurs: list[Slur] = _contexts(document=document, kind=Slur)
    assert [slur.voice for slur in slurs] == list(document.voices)
    assert {
        (
            document.measures.index(slur.start.measure),
            document.measures.index(slur.end.measure),
        )
        for slur in slurs
    } == {(1, 2)}

    log.rollback()
    assert _contexts(document=document, kind=Slur) == []


def test_a_mark_names_at_least_one_voice_each_once() -> None:
    document: ScoreDocument = score()
    first: str = document.voices[0].id

    for voice_ids in ((), (first, first)):
        with pytest.raises(MutationRejectedError, match="at least one voice, each once"):
            _run(
                document=document,
                intent=CreateSlurIntent(
                    start_measure_id=document.measures[1].id,
                    start_position=_START,
                    end_measure_id=document.measures[2].id,
                    end_position=_START,
                    voice_ids=voice_ids,
                ),
            )

    assert _contexts(document=document, kind=Slur) == []


def test_slurs_may_nest_but_one_cannot_end_before_it_starts() -> None:
    document: ScoreDocument = score()
    voices: tuple[str, ...] = (document.voices[0].id,)
    outer: CreateSlurIntent = CreateSlurIntent(
        start_measure_id=document.measures[1].id,
        start_position=_START,
        end_measure_id=document.measures[2].id,
        end_position=_START,
        voice_ids=voices,
    )
    inner: CreateSlurIntent = CreateSlurIntent(
        start_measure_id=document.measures[1].id,
        start_position=_BEAT_TWO,
        end_measure_id=document.measures[1].id,
        end_position=MeasurePosition.of(numerator=1, denominator=2),
        voice_ids=voices,
    )
    _run(document=document, intent=outer)
    _run(document=document, intent=inner)
    assert len(_contexts(document=document, kind=Slur)) == 2

    with pytest.raises(MutationRejectedError, match="must end after it starts"):
        _run(
            document=document,
            intent=CreateSlurIntent(
                start_measure_id=document.measures[1].id,
                start_position=_BEAT_TWO,
                end_measure_id=document.measures[1].id,
                end_position=_START,
                voice_ids=voices,
            ),
        )

    assert len(_contexts(document=document, kind=Slur)) == 2


def test_an_octave_line_made_keeping_the_steps_leaves_the_notes_and_changes_their_sound() -> None:
    document: ScoreDocument = score()
    inside: Note = note(document, Fraction(1) + Fraction(1, 4), step=-2)
    outside: Note = note(document, Fraction(1, 4), step=-2)
    sounded_inside: int = _midi(document=document, target=inside)
    sounded_outside: int = _midi(document=document, target=outside)

    _run(
        document=document,
        intent=_octave(document=document, start=_START, mode=PitchEditMode.PRESERVE_STEP),
    )

    (line,) = _contexts(document=document, kind=OctaveTransposition)
    assert line.octaves == 1
    assert inside.staff_step == -2
    assert _midi(document=document, target=inside) == sounded_inside + 12
    assert _midi(document=document, target=outside) == sounded_outside


def test_an_octave_line_made_keeping_the_pitch_moves_the_notes_to_steps_that_sound_as_before() -> (
    None
):
    document: ScoreDocument = score()
    inside: Note = note(document, Fraction(1) + Fraction(1, 4), step=-2)
    sounded: int = _midi(document=document, target=inside)

    _run(
        document=document,
        intent=_octave(document=document, start=_START, mode=PitchEditMode.PRESERVE_PITCH),
    )

    assert inside.staff_step != -2
    assert _midi(document=document, target=inside) == sounded


def test_an_octave_line_over_another_on_the_same_staff_is_refused() -> None:
    document: ScoreDocument = score()
    _run(
        document=document,
        intent=_octave(document=document, start=_START, mode=PitchEditMode.PRESERVE_STEP),
    )

    with pytest.raises(MutationRejectedError, match="cannot overlap another"):
        _run(
            document=document,
            intent=_octave(document=document, start=_BEAT_TWO, mode=PitchEditMode.PRESERVE_STEP),
        )

    assert len(_contexts(document=document, kind=OctaveTransposition)) == 1


def test_an_octave_line_deleted_keeping_the_steps_makes_the_notes_sound_as_written() -> None:
    document: ScoreDocument = score()
    inside: Note = note(document, Fraction(1) + Fraction(1, 4), step=-2)
    written: int = _midi(document=document, target=inside)
    _run(
        document=document,
        intent=_octave(document=document, start=_START, mode=PitchEditMode.PRESERVE_STEP),
    )
    (line,) = _contexts(document=document, kind=OctaveTransposition)

    log: MutationLog = _run(
        document=document,
        intent=DeleteOctaveTranspositionIntent(octave_id=line.id, mode=PitchEditMode.PRESERVE_STEP),
    )

    assert _contexts(document=document, kind=OctaveTransposition) == []
    assert _midi(document=document, target=inside) == written

    log.rollback()
    assert _contexts(document=document, kind=OctaveTransposition) == [line]
    assert _midi(document=document, target=inside) == written + 12


def test_an_octave_line_deleted_keeping_the_pitch_moves_the_notes_to_keep_their_sound() -> None:
    document: ScoreDocument = score()
    inside: Note = note(document, Fraction(1) + Fraction(1, 4), step=-2)
    _run(
        document=document,
        intent=_octave(document=document, start=_START, mode=PitchEditMode.PRESERVE_STEP),
    )
    (line,) = _contexts(document=document, kind=OctaveTransposition)
    sounded: int = _midi(document=document, target=inside)

    _run(
        document=document,
        intent=DeleteOctaveTranspositionIntent(
            octave_id=line.id, mode=PitchEditMode.PRESERVE_PITCH
        ),
    )

    assert inside.staff_step != -2
    assert _midi(document=document, target=inside) == sounded


def test_a_tempo_transition_is_made_as_the_ratio_of_the_target_to_the_tempo_it_starts_at() -> None:
    document: ScoreDocument = score()

    log: MutationLog = _run(
        document=document, intent=_transition(document=document, target_bpm=120)
    )

    (transition,) = _contexts(document=document, kind=TempoTransition)
    assert transition.ratio == Fraction(120, _INITIAL_BPM)

    log.rollback()
    assert _contexts(document=document, kind=TempoTransition) == []


def test_a_tempo_transition_to_the_tempo_it_starts_at_is_refused() -> None:
    document: ScoreDocument = score()

    with pytest.raises(MutationRejectedError, match="must change the tempo"):
        _run(document=document, intent=_transition(document=document, target_bpm=_INITIAL_BPM))

    assert _contexts(document=document, kind=TempoTransition) == []


def test_a_tempo_transition_to_less_than_one_beat_a_minute_is_refused() -> None:
    document: ScoreDocument = score()

    with pytest.raises(MutationRejectedError, match="at least 1 beat per minute"):
        _run(document=document, intent=_transition(document=document, target_bpm=0))

    assert _contexts(document=document, kind=TempoTransition) == []


def test_a_tempo_transition_over_another_is_refused() -> None:
    document: ScoreDocument = score()
    _run(document=document, intent=_transition(document=document, target_bpm=120))

    with pytest.raises(MutationRejectedError, match="cannot overlap another"):
        _run(
            document=document,
            intent=CreateTempoTransitionIntent(
                start_measure_id=document.measures[1].id,
                start_position=_BEAT_TWO,
                end_measure_id=document.measures[2].id,
                end_position=_START,
                target_bpm=60,
            ),
        )

    assert len(_contexts(document=document, kind=TempoTransition)) == 1


def test_a_new_target_of_a_tempo_transition_changes_its_ratio() -> None:
    document: ScoreDocument = score()
    _run(document=document, intent=_transition(document=document, target_bpm=120))
    (transition,) = _contexts(document=document, kind=TempoTransition)

    log: MutationLog = _run(
        document=document,
        intent=SetTempoTransitionTargetIntent(transition_id=transition.id, target_bpm=180),
    )

    assert transition.ratio == Fraction(180, _INITIAL_BPM)

    log.rollback()
    assert transition.ratio == Fraction(120, _INITIAL_BPM)


def test_a_new_target_of_a_tempo_transition_at_the_tempo_it_starts_at_is_refused() -> None:
    document: ScoreDocument = score()
    _run(document=document, intent=_transition(document=document, target_bpm=120))
    (transition,) = _contexts(document=document, kind=TempoTransition)

    with pytest.raises(MutationRejectedError, match="must change the tempo"):
        _run(
            document=document,
            intent=SetTempoTransitionTargetIntent(
                transition_id=transition.id, target_bpm=_INITIAL_BPM
            ),
        )

    assert transition.ratio == Fraction(120, _INITIAL_BPM)


def _sustain(
    *, document: ScoreDocument, start: tuple[int, MeasurePosition], end: tuple[int, MeasurePosition]
) -> CreateSustainHoldIntent:
    return CreateSustainHoldIntent(
        start_measure_id=document.measures[start[0]].id,
        start_position=start[1],
        end_measure_id=document.measures[end[0]].id,
        end_position=end[1],
    )


def test_a_sustain_hold_is_put_between_the_places_it_names() -> None:
    document: ScoreDocument = score()

    log: MutationLog = _run(
        document=document,
        intent=_sustain(document=document, start=(1, _START), end=(2, _START)),
    )

    (hold,) = _contexts(document=document, kind=SustainHold)
    assert (
        document.measures.index(hold.start.measure),
        document.measures.index(hold.end.measure),
    ) == (1, 2)

    log.rollback()
    assert _contexts(document=document, kind=SustainHold) == []


def test_a_sustain_hold_over_another_is_refused() -> None:
    document: ScoreDocument = score()
    _run(document=document, intent=_sustain(document=document, start=(1, _START), end=(2, _START)))

    with pytest.raises(MutationRejectedError, match="cannot overlap another"):
        _run(
            document=document,
            intent=_sustain(document=document, start=(1, _BEAT_TWO), end=(2, _BEAT_TWO)),
        )

    assert len(_contexts(document=document, kind=SustainHold)) == 1


def test_a_sustain_hold_may_start_where_the_last_one_ends() -> None:
    """Letting go and pressing again at the barline is a change of pedal."""
    document: ScoreDocument = score()
    _run(document=document, intent=_sustain(document=document, start=(0, _START), end=(1, _START)))

    _run(document=document, intent=_sustain(document=document, start=(1, _START), end=(2, _START)))

    assert len(_contexts(document=document, kind=SustainHold)) == 2


def test_a_sustain_hold_cannot_end_before_it_starts() -> None:
    document: ScoreDocument = score()

    with pytest.raises(MutationRejectedError, match="must end after it starts"):
        _run(
            document=document,
            intent=_sustain(document=document, start=(1, _BEAT_TWO), end=(1, _START)),
        )

    assert _contexts(document=document, kind=SustainHold) == []


def test_moving_the_end_of_a_sustain_hold_over_the_next_one_is_refused() -> None:
    document: ScoreDocument = score()
    _run(document=document, intent=_sustain(document=document, start=(0, _START), end=(1, _START)))
    _run(document=document, intent=_sustain(document=document, start=(1, _START), end=(2, _START)))
    first, _second = _contexts(document=document, kind=SustainHold)

    with pytest.raises(MutationRejectedError, match="cannot overlap another"):
        _run(
            document=document,
            intent=MoveContextEndIntent(
                context_ids=(first.id,),
                measure_id=document.measures[1].id,
                position=_BEAT_TWO,
                mode=PitchEditMode.PRESERVE_STEP,
            ),
        )

    assert document.measures.index(first.end.measure) == 1


def test_moving_the_start_of_a_sustain_hold_over_the_last_one_is_refused() -> None:
    document: ScoreDocument = score()
    _run(document=document, intent=_sustain(document=document, start=(0, _START), end=(1, _START)))
    _run(document=document, intent=_sustain(document=document, start=(1, _START), end=(2, _START)))
    _first, second = _contexts(document=document, kind=SustainHold)

    with pytest.raises(MutationRejectedError, match="cannot overlap another"):
        _run(
            document=document,
            intent=MoveContextStartIntent(
                context_ids=(second.id,),
                measure_id=document.measures[0].id,
                position=_BEAT_TWO,
                mode=PitchEditMode.PRESERVE_STEP,
            ),
        )

    assert document.measures.index(second.start.measure) == 1


def test_a_sustain_hold_is_deleted_and_its_deletion_is_undone() -> None:
    document: ScoreDocument = score()
    _run(document=document, intent=_sustain(document=document, start=(1, _START), end=(2, _START)))
    (hold,) = _contexts(document=document, kind=SustainHold)

    log: MutationLog = _run(document=document, intent=DeleteBatchIntent(entity_ids=(hold.id,)))
    assert _contexts(document=document, kind=SustainHold) == []

    log.rollback()
    assert _contexts(document=document, kind=SustainHold) == [hold]


_END_OF_MEASURE: MeasurePosition = MeasurePosition.of(numerator=1, denominator=1)


def _span_of_every_kind(*, document: ScoreDocument) -> dict[type[Context], EditIntent]:
    """One span of each kind, from the second measure to the third."""
    return {
        Slur: CreateSlurIntent(
            start_measure_id=document.measures[1].id,
            start_position=_START,
            end_measure_id=document.measures[2].id,
            end_position=_START,
            voice_ids=(document.voices[0].id,),
        ),
        Hairpin: _hairpin(document=document, target=DynamicMarking.FORTE),
        OctaveTransposition: _octave(
            document=document, start=_START, mode=PitchEditMode.PRESERVE_STEP
        ),
        SustainHold: _sustain(document=document, start=(1, _START), end=(2, _START)),
        TempoTransition: _transition(document=document, target_bpm=120),
    }


@pytest.mark.parametrize("kind", [Slur, Hairpin, OctaveTransposition, SustainHold, TempoTransition])
def test_moving_the_start_of_a_span_to_the_end_of_a_measure_is_refused(
    kind: type[Context],
) -> None:
    """The end of a measure is the moment the next one starts: no place for a start."""
    document: ScoreDocument = score()
    _run(document=document, intent=_span_of_every_kind(document=document)[kind])
    (span,) = _contexts(document=document, kind=kind)

    with pytest.raises(MutationRejectedError, match="at or past the end of the measure"):
        _run(
            document=document,
            intent=MoveContextStartIntent(
                context_ids=(span.id,),
                measure_id=document.measures[1].id,
                position=_END_OF_MEASURE,
                mode=PitchEditMode.PRESERVE_STEP,
            ),
        )

    assert document.measures.index(span.start.measure) == 1
    assert span.start.position == _START


@pytest.mark.parametrize("kind", [Slur, Hairpin, OctaveTransposition, SustainHold, TempoTransition])
def test_moving_the_end_of_a_span_to_the_end_of_a_measure_is_refused(
    kind: type[Context],
) -> None:
    document: ScoreDocument = score()
    _run(document=document, intent=_span_of_every_kind(document=document)[kind])
    (span,) = _contexts(document=document, kind=kind)

    with pytest.raises(MutationRejectedError, match="at or past the end of the measure"):
        _run(
            document=document,
            intent=MoveContextEndIntent(
                context_ids=(span.id,),
                measure_id=document.measures[2].id,
                position=_END_OF_MEASURE,
                mode=PitchEditMode.PRESERVE_STEP,
            ),
        )

    assert document.measures.index(span.end.measure) == 2
    assert span.end.position == _START
