from fractions import Fraction

import pytest

from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.notation import RhythmicValue

from ...domain.scene import Score, build_score, insert_note, layout

# A rest is stored with its staff only — where it is drawn on the staff is the renderer's;
# a note keeps its staff step.


@pytest.mark.unit
def test_notes_and_rests_survive_a_round_trip() -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    score: Score = build_score(measure_count=1)
    insert_note(score=score, at=Fraction(1, 4), rhythmic_value=RhythmicValue.QUARTER, step=5)

    serialized = codec.serialize(score.document)
    decoded: ScoreDocument = codec.deserialize(serialized)

    rests = [row for row in serialized["tables"]["musical_items"].values() if row["kind"] == "rest"]
    notes = [row for row in serialized["tables"]["musical_items"].values() if row["kind"] == "note"]
    assert rests and all("staff_step" not in row for row in rests)
    assert [row["staff_step"] for row in notes] == [5]
    assert codec.serialize(decoded) == serialized
    assert layout(
        score=Score(
            document=decoded,
            voice=decoded.voices[0],
            staff=decoded.staffs[0],
            measures=list(decoded.measures),
        )
    ) == layout(score=score)
