import pytest

from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.models.notation import StemDirection, StemOverride
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer

from ...domain.scene import Score, build_score, quarters

# A stem override is saved with its note carrier. Compared by value: the override is a
# value object, so equality there does prove the content survived.


def _stems(*, document: ScoreDocument) -> list[StemOverride | None]:
    stems: list[StemOverride | None] = []
    for child in document.voices[0].children:
        assert isinstance(child, LeafRhythmicContainer)
        assert isinstance(child.carrier, NoteCarrier)
        stems.append(child.carrier.stem)

    return stems


@pytest.mark.unit
def test_stem_overrides_survive_a_round_trip() -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0)
    carriers: list[NoteCarrier] = []
    for child in score.voice.children:
        assert isinstance(child, LeafRhythmicContainer)
        assert isinstance(child.carrier, NoteCarrier)
        carriers.append(child.carrier)
    carriers[0].set_stem(stem=StemOverride(direction=StemDirection.UP, length_percent=150))
    carriers[3].set_stem(stem=StemOverride(direction=StemDirection.DOWN))

    decoded: ScoreDocument = codec.deserialize(codec.serialize(score.document))

    assert _stems(document=decoded) == _stems(document=score.document)
    assert codec.serialize(decoded) == codec.serialize(score.document)
