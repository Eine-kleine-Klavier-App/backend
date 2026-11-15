from fractions import Fraction

import pytest

from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.models.notation import Accidental, RhythmicValue
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer

from ...domain.scene import Score, build_score, insert_note, note_at

# A note keeps its explicit accidental in the record, the double ones included.


def _accidentals(*, document: ScoreDocument) -> list[Accidental]:
    accidentals: list[Accidental] = []
    for child in document.voices[0].children:
        assert isinstance(child, LeafRhythmicContainer)
        if isinstance(child.carrier, NoteCarrier):
            accidentals.extend(note.accidental for note in child.carrier.notes)

    return accidentals


@pytest.mark.unit
@pytest.mark.parametrize("accidental", list(Accidental))
def test_every_accidental_survives_a_round_trip(accidental: Accidental) -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    score: Score = build_score(measure_count=1)
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, step=3)
    note_at(score=score, at=Fraction(0)).set_accidental(accidental=accidental)

    decoded: ScoreDocument = codec.deserialize(codec.serialize(score.document))

    assert _accidentals(document=decoded) == [accidental]
    assert codec.serialize(decoded) == codec.serialize(score.document)
