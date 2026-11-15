import json
from collections.abc import Callable
from fractions import Fraction

import pytest

from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Carrier
from piano_app.domain.score.document.models.notation import RhythmicSize, RhythmicValue
from piano_app.domain.score.document.models.relations import Beam
from piano_app.domain.score.document.services.helpers import find_beams
from piano_app.domain.score.document.services.mutation.compiler import (
    AppendMeasureIntent,
    ChangeTimeSignatureIntent,
    CreateBeamIntent,
    EditIntent,
    InsertMeasureIntent,
    RemoveMeasureIntent,
)

from ...domain.scene import (
    Score,
    apply_intent,
    build_score,
    create_tuplet_with_note,
    crossing_triplet,
    insert_note,
    note,
    note_at,
    quarters,
    refresh_score,
    signatures,
    size,
    value,
)

# A document re-serialised after decoding must come out byte for byte the same: the codec
# restores each anchor's containers in the order it stored them, so that order must already
# be the one restoring produces — every container after the containers holding it.


def _insert_before_second(score: Score) -> EditIntent:
    return InsertMeasureIntent(before_measure_id=score.measures[1].id)


def _remove_first(score: Score) -> EditIntent:
    return RemoveMeasureIntent(measure_id=score.measures[0].id)


def _append(score: Score) -> EditIntent:
    return AppendMeasureIntent()


def _three_four_on_first(score: Score) -> EditIntent:
    three_four: RhythmicSize = size(RhythmicValue.QUARTER, count=3)
    return ChangeTimeSignatureIntent(measure_ids=(score.measures[0].id,), time_signature=three_four)


def _two_four_on_second(score: Score) -> EditIntent:
    two_four: RhythmicSize = size(RhythmicValue.QUARTER, count=2)
    return ChangeTimeSignatureIntent(measure_ids=(score.measures[1].id,), time_signature=two_four)


@pytest.mark.unit
@pytest.mark.parametrize(
    "make_intent",
    [_insert_before_second, _remove_first, _append, _three_four_on_first, _two_four_on_second],
    ids=[
        "insert-splitting-a-tuplet",
        "remove-splitting-a-tuplet",
        "append",
        "time-signature-splitting-a-tuplet-at-the-end",
        "time-signature-splitting-a-tuplet-at-the-start",
    ],
)
def test_a_document_after_a_measure_operation_re_serialises_byte_for_byte(
    make_intent: Callable[[Score], EditIntent],
) -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    score: Score = crossing_triplet()

    apply_intent(score=score, intent=make_intent(score))

    encoded: str = json.dumps(codec.serialize(score.document))
    decoded: ScoreDocument = codec.deserialize(codec.serialize(score.document))
    assert json.dumps(codec.serialize(decoded)) == encoded


@pytest.mark.unit
def test_a_document_after_a_beam_is_cut_in_two_re_serialises_byte_for_byte() -> None:
    """Six beamed eighths with a quarter over the middle two: two beams after the cut."""
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    score: Score = build_score(measure_count=1)
    for index in range(6):
        note(
            score=score,
            parent=score.voice,
            at=index * Fraction(1, 8),
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index + 1,
        )
    quarters(score=score, measure=0, beats=(3,))
    Beam.create(
        carriers=[
            note_at(score=score, at=index * Fraction(1, 8)).note_carrier for index in range(6)
        ]
    )
    insert_note(score=score, at=Fraction(1, 4), rhythmic_value=RhythmicValue.QUARTER)

    encoded: str = json.dumps(codec.serialize(score.document))
    decoded: ScoreDocument = codec.deserialize(codec.serialize(score.document))
    assert json.dumps(codec.serialize(decoded)) == encoded
    assert encoded.count('"kind": "beam"') == 2


@pytest.mark.unit
def test_a_draft_edited_through_the_new_intents_re_serialises_byte_for_byte() -> None:
    """Four eighths beamed through the intent, a triplet of eighths after them, and measure two
    — a quarter on its first beat — turned into 3/4, which adds a measure."""
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    score: Score = build_score(measure_count=2)
    for index in range(4):
        insert_note(
            score=score,
            at=index * Fraction(1, 8),
            rhythmic_value=RhythmicValue.EIGHTH,
            step=index + 1,
        )
    beamed: list[Carrier] = [
        note_at(score=score, at=index * Fraction(1, 8)).note_carrier for index in range(4)
    ]
    apply_intent(
        score=score,
        intent=CreateBeamIntent(carrier_ids=tuple(carrier.id for carrier in beamed)),
    )
    create_tuplet_with_note(
        score=score,
        at=Fraction(1, 2),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.EIGHTH, count=2),
        first=value(RhythmicValue.EIGHTH),
    )
    insert_note(score=score, at=Fraction(1), rhythmic_value=RhythmicValue.QUARTER)
    apply_intent(
        score=score,
        intent=ChangeTimeSignatureIntent(
            measure_ids=(score.measures[1].id,),
            time_signature=size(RhythmicValue.QUARTER, count=3),
        ),
    )

    encoded: str = json.dumps(codec.serialize(score.document))
    decoded: ScoreDocument = codec.deserialize(codec.serialize(score.document))
    assert json.dumps(codec.serialize(decoded)) == encoded
    assert [list(beam.members) for beam in find_beams(carriers=beamed)] == [beamed]
    assert encoded.count('"kind": "beam"') == 1
    assert encoded.count('"kind": "group"') == 1
    assert signatures(score=refresh_score(score=score)) == [
        Fraction(1),
        Fraction(3, 4),
        Fraction(3, 4),
    ]
