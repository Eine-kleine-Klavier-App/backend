import pytest

from piano_app.application.use_cases.score.shared import ScoreView
from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.models.notation import StemDirection, StemOverride
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer

from ..domain.scene import Score, build_score, quarters


@pytest.mark.unit
def test_a_chord_carrier_in_the_view_carries_its_stem_or_null() -> None:
    score: Score = build_score(bars=1)
    quarters(score=score, bar=0, beats=(0, 1))
    carriers: list[NoteCarrier] = []
    for child in score.voice.children:
        assert isinstance(child, LeafRhythmicContainer)
        assert isinstance(child.carrier, NoteCarrier)
        carriers.append(child.carrier)
    carriers[0].set_stem(stem=StemOverride(direction=StemDirection.DOWN, length_percent=80))

    view: dict[str, object] = ScoreView(document=score.document).jsonify()

    chords = view["carriers"]
    assert isinstance(chords, list)
    stems: dict[str, object] = {chord["id"]: chord["stem"] for chord in chords}
    assert stems == {
        carriers[0].id: {"direction": "down", "length_percent": 80},
        carriers[1].id: None,
    }
