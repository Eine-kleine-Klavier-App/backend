import pytest

from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.models.notation import Ornament
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer

from ...domain.scene import Score, build_score, quarters

# An ornament is saved with its note carrier; a score saved before ornaments existed reads as
# having none.


def _ornaments(*, document: ScoreDocument) -> list[Ornament]:
    ornaments: list[Ornament] = []
    for child in document.voices[0].children:
        assert isinstance(child, LeafRhythmicContainer)
        assert isinstance(child.carrier, NoteCarrier)
        ornaments.append(child.carrier.ornament)

    return ornaments


def _scored() -> Score:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    carriers: list[NoteCarrier] = []
    for child in score.document.voices[0].children:
        assert isinstance(child, LeafRhythmicContainer)
        assert isinstance(child.carrier, NoteCarrier)
        carriers.append(child.carrier)
    carriers[1].set_ornament(ornament=Ornament.TRILL)
    carriers[2].set_ornament(ornament=Ornament.TREMOLO_3)
    carriers[3].set_ornament(ornament=Ornament.INVERTED_TURN)

    return score


@pytest.mark.unit
def test_ornaments_survive_a_round_trip() -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    score: Score = _scored()

    decoded: ScoreDocument = codec.deserialize(codec.serialize(score.document))

    assert _ornaments(document=decoded) == [
        Ornament.NONE,
        Ornament.TRILL,
        Ornament.TREMOLO_3,
        Ornament.INVERTED_TURN,
    ]
    assert codec.serialize(decoded) == codec.serialize(score.document)


@pytest.mark.unit
def test_a_score_saved_without_ornaments_reads_as_having_none() -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    data = codec.serialize(_scored().document)
    for row in data["carriers"]:
        row.pop("ornament", None)

    decoded: ScoreDocument = codec.deserialize(data)

    assert _ornaments(document=decoded) == [Ornament.NONE] * 4
