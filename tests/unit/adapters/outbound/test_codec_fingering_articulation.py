import pytest

from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.models.notation import Articulation, Fingering
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer

from ...domain.scene import Score, build_score, quarters

# A fingering is saved with its note and an articulation with its note carrier.


def _carriers(*, document: ScoreDocument) -> list[NoteCarrier]:
    carriers: list[NoteCarrier] = []
    for child in document.voices[0].children:
        assert isinstance(child, LeafRhythmicContainer)
        assert isinstance(child.carrier, NoteCarrier)
        carriers.append(child.carrier)

    return carriers


def _markings(*, document: ScoreDocument) -> list[tuple[frozenset[Articulation], list[Fingering]]]:
    markings: list[tuple[frozenset[Articulation], list[Fingering]]] = []
    for carrier in _carriers(document=document):
        markings.append((carrier.articulations, [note.fingering for note in carrier.notes]))

    return markings


@pytest.mark.unit
def test_fingerings_and_articulations_survive_a_round_trip() -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    carriers: list[NoteCarrier] = _carriers(document=score.document)
    carriers[0].notes[0].set_fingering(fingering=Fingering.THUMB)
    carriers[1].set_articulations(articulations=frozenset({Articulation.STACCATO}))
    carriers[3].notes[0].set_fingering(fingering=Fingering.LITTLE)
    carriers[3].set_articulations(
        articulations=frozenset({Articulation.FERMATA, Articulation.ACCENT})
    )

    decoded: ScoreDocument = codec.deserialize(codec.serialize(score.document))

    assert _markings(document=decoded) == [
        (frozenset(), [Fingering.THUMB]),
        (frozenset({Articulation.STACCATO}), [Fingering.NONE]),
        (frozenset(), [Fingering.NONE]),
        (
            frozenset({Articulation.FERMATA, Articulation.ACCENT}),
            [Fingering.LITTLE],
        ),
    ]
    assert codec.serialize(decoded) == codec.serialize(score.document)
