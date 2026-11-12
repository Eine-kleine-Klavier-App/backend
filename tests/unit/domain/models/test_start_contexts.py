import pytest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import (
    ClefChange,
    Context,
    DynamicChange,
    KeySignatureChange,
    TempoChange,
)
from piano_app.domain.score.document.models.notation import (
    Clef,
    DynamicMarking,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural import (
    MEASURE_START,
    Measure,
    Staff,
    Voice,
)

# What every score holds at its very start, and how a score is made to hold it: the single
# entry that creates a score, and the check on one assembled or loaded from parts.


def _start_contexts(document: ScoreDocument) -> list[Context]:
    return list(document.measures[0].anchors[0].starting_contexts)


@pytest.mark.unit
def test_a_fresh_score_has_the_requested_voices_staffs_and_measures() -> None:
    document: ScoreDocument = ScoreDocument.create_fresh(
        voice_count=3, staff_count=2, measure_count=5
    )

    assert (len(document.voices), len(document.staffs), len(document.measures)) == (3, 2, 5)


@pytest.mark.unit
def test_a_fresh_score_starts_with_a_clef_and_a_key_signature_on_each_staff() -> None:
    document: ScoreDocument = ScoreDocument.create_fresh(
        voice_count=1, staff_count=3, measure_count=2
    )

    clefs: dict[Staff, Clef] = {
        context.staff: context.clef
        for context in _start_contexts(document)
        if isinstance(context, ClefChange)
    }
    key_signatures: list[KeySignatureChange] = [
        context for context in _start_contexts(document) if isinstance(context, KeySignatureChange)
    ]

    assert [clefs[staff] for staff in document.staffs] == [Clef.TREBLE, Clef.BASS, Clef.BASS]
    assert {change.staff for change in key_signatures} == set(document.staffs)
    assert all(
        all(alteration.value == "natural" for alteration in change.alterations)
        for change in key_signatures
    )


@pytest.mark.unit
def test_a_fresh_score_starts_with_a_dynamic_on_each_voice_and_one_tempo() -> None:
    document: ScoreDocument = ScoreDocument.create_fresh(
        voice_count=3, staff_count=1, measure_count=1
    )

    dynamics: list[DynamicChange] = [
        context for context in _start_contexts(document) if isinstance(context, DynamicChange)
    ]
    tempos: list[TempoChange] = [
        context for context in _start_contexts(document) if isinstance(context, TempoChange)
    ]

    assert sorted(voice.id for change in dynamics for voice in change.voices) == sorted(
        voice.id for voice in document.voices
    )
    assert len(dynamics) == 1
    assert dynamics[0].voices == list(document.voices)
    assert {change.dynamic for change in dynamics} == {DynamicMarking.PIANO}
    assert len(tempos) == 1
    assert (tempos[0].beat.value, tempos[0].beat.dots_count, tempos[0].bpm) == (
        RhythmicValue.QUARTER,
        0,
        90,
    )


@pytest.mark.unit
def test_every_start_context_lies_at_the_very_start_of_the_first_measure() -> None:
    document: ScoreDocument = ScoreDocument.create_fresh(
        voice_count=2, staff_count=2, measure_count=3
    )

    assert len(document.measures[0].anchors) == 1
    assert document.measures[0].anchors[0].position == MEASURE_START
    assert all(not measure.anchors for measure in document.measures[1:])
    assert len(_start_contexts(document)) == 1 + 2 * 2 + 1


@pytest.mark.unit
def test_a_fresh_score_lacks_nothing() -> None:
    assert (
        ScoreDocument.create_fresh(
            voice_count=2, staff_count=2, measure_count=2
        ).missing_initial_contexts()
        == []
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("voices", "staffs", "measures"), [(0, 1, 1), (1, 0, 1), (1, 1, 0), (-1, 1, 1)]
)
def test_a_fresh_score_needs_a_voice_a_staff_and_a_measure(
    voices: int, staffs: int, measures: int
) -> None:
    with pytest.raises(ValueError, match="at least one voice, one staff and one measure"):
        ScoreDocument.create_fresh(voice_count=voices, staff_count=staffs, measure_count=measures)


@pytest.mark.unit
def test_a_score_assembled_from_parts_lacks_everything_until_the_start_contexts_are_placed() -> (
    None
):
    voice, staff = Voice(), Staff()
    document: ScoreDocument = ScoreDocument.create(
        voices=[voice], staffs=[staff], measures=[Measure.create()]
    )

    assert document.missing_initial_contexts() == [
        "tempo",
        f"clef of staff {staff.id}",
        f"key signature of staff {staff.id}",
        f"dynamic of voice {voice.id}",
    ]

    document.place_start_contexts()

    assert document.missing_initial_contexts() == []


@pytest.mark.unit
def test_a_score_with_no_measure_lacks_the_tempo_and_the_rest() -> None:
    document: ScoreDocument = ScoreDocument.create(voices=[Voice()], staffs=[Staff()], measures=[])

    assert document.missing_initial_contexts()[0] == "tempo"
    assert len(document.missing_initial_contexts()) == 4


@pytest.mark.unit
@pytest.mark.parametrize("kind", [TempoChange, ClefChange, KeySignatureChange, DynamicChange])
def test_taking_any_one_start_context_away_is_noticed(kind: type[Context]) -> None:
    document: ScoreDocument = ScoreDocument.create_fresh(
        voice_count=1, staff_count=1, measure_count=1
    )
    context: Context = next(
        context for context in _start_contexts(document) if isinstance(context, kind)
    )

    context.detach()

    assert len(document.missing_initial_contexts()) == 1
