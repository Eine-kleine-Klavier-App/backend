import json
from typing import Any

import pytest
from tests.fixtures.records import as_stored

from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import Note, NoteCarrier
from piano_app.domain.score.document.models.notation import (
    Accidental,
    GlissandoType,
)
from piano_app.domain.score.document.models.relations import (
    Beam,
    Glissando,
    Relation,
    Tie,
)
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer

from ...domain.scene import Score, build_score, quarters

# A glissando is saved with its two notes and its type. Compared structurally: a decoded
# relation keeps its id, so entity equality would hold even if its members or type decoded wrong.

type RelationShape = tuple[str, str, tuple[str, ...], str | None]


def _carriers(*, document: ScoreDocument) -> list[NoteCarrier]:
    carriers: list[NoteCarrier] = []
    for child in document.voices[0].children:
        assert isinstance(child, LeafRhythmicContainer)
        assert isinstance(child.carrier, NoteCarrier)
        carriers.append(child.carrier)

    return carriers


def _relation_shape(*, relation: Relation) -> RelationShape:
    if isinstance(relation, Tie):
        return ("tie", relation.id, (relation.start.id, relation.end.id), None)

    if isinstance(relation, Glissando):
        return (
            "glissando",
            relation.id,
            (relation.start.id, relation.end.id),
            relation.glissando_type.value,
        )

    if isinstance(relation, Beam):
        return ("beam", relation.id, tuple(member.id for member in relation.members), None)

    raise TypeError(f"Unexpected relation type: {type(relation).__name__}.")


def _relation_layout(*, document: ScoreDocument) -> list[list[RelationShape]]:
    """Every carrier's group relations, then each of its notes' relations, in back-reference
    order."""
    layout: list[list[RelationShape]] = []
    for carrier in _carriers(document=document):
        carrier_relations: list[RelationShape] = []
        for carrier_relation in carrier.carrier_group_relations:
            carrier_relations.append(_relation_shape(relation=carrier_relation))
        layout.append(carrier_relations)

        for note in carrier.notes:
            note_relations: list[RelationShape] = []
            for note_relation in note.relations:
                note_relations.append(_relation_shape(relation=note_relation))
            layout.append(note_relations)

    return layout


def _score_with_chords() -> Score:
    """Four quarters; the first two carriers are two-note chords."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    carriers: list[NoteCarrier] = _carriers(document=score.document)
    for carrier in carriers[:2]:
        Note.create(
            note_carrier=carrier,
            staff=score.staff,
            staff_step=4,
            accidental=Accidental.NATURAL,
        )

    return score


def _bytes(*, data: dict[str, Any]) -> str:
    return json.dumps(data)


@pytest.mark.unit
def test_a_glissando_survives_a_round_trip_with_its_type() -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    score: Score = _score_with_chords()
    carriers: list[NoteCarrier] = _carriers(document=score.document)
    glissando: Glissando = Glissando.create(
        start_note=carriers[2].notes[0],
        end_note=carriers[3].notes[0],
        glissando_type=GlissandoType.WAVY,
    )

    decoded: ScoreDocument = codec.deserialize(codec.serialize(score.document))

    decoded_carriers: list[NoteCarrier] = _carriers(document=decoded)
    decoded_glissando: Relation = decoded_carriers[2].notes[0].relations[0]
    assert isinstance(decoded_glissando, Glissando)
    assert decoded_glissando.id == glissando.id
    assert decoded_glissando.glissando_type is GlissandoType.WAVY
    assert decoded_glissando.start is decoded_carriers[2].notes[0]
    assert decoded_glissando.end is decoded_carriers[3].notes[0]
    assert list(decoded_carriers[3].notes[0].relations) == [decoded_glissando]
    assert _relation_layout(document=decoded) == _relation_layout(document=score.document)


def _relation_kinds(*, record: dict[str, Any]) -> list[str]:
    """The kinds of a record's relations, in the order the record lists them."""
    return [
        record["tables"]["relations"][relation_id]["kind"] for relation_id in record["relation_ids"]
    ]


@pytest.mark.unit
def test_glissandos_mixed_with_ties_and_beams_round_trip_canonically() -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    score: Score = _score_with_chords()
    carriers: list[NoteCarrier] = _carriers(document=score.document)
    Tie.create(start_note=carriers[0].notes[0], end_note=carriers[1].notes[0])
    Glissando.create(
        start_note=carriers[0].notes[1],
        end_note=carriers[1].notes[1],
        glissando_type=GlissandoType.WAVY,
    )
    Glissando.create(
        start_note=carriers[1].notes[0],
        end_note=carriers[2].notes[0],
        glissando_type=GlissandoType.STRAIGHT,
    )
    Beam.create(carriers=[carriers[0], carriers[1]])

    encoded: dict[str, Any] = codec.serialize(score.document)
    decoded: ScoreDocument = codec.deserialize(encoded)
    re_encoded: dict[str, Any] = codec.serialize(decoded)

    assert [
        encoded["tables"]["relations"][relation_id]["kind"]
        for relation_id in encoded["relation_ids"]
    ] == [
        "beam",
        "tie",
        "glissando",
        "glissando",
    ]
    assert _relation_layout(document=decoded) == _relation_layout(document=score.document)
    assert _bytes(data=re_encoded) == _bytes(data=encoded)
    assert _bytes(data=codec.serialize(codec.deserialize(re_encoded))) == _bytes(data=encoded)


@pytest.mark.unit
def test_a_record_whose_keys_a_store_reordered_reads_back_the_same() -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    score: Score = _score_with_chords()
    carriers: list[NoteCarrier] = _carriers(document=score.document)
    Tie.create(start_note=carriers[0].notes[0], end_note=carriers[1].notes[0])
    Glissando.create(
        start_note=carriers[0].notes[1],
        end_note=carriers[1].notes[1],
        glissando_type=GlissandoType.WAVY,
    )
    Beam.create(carriers=[carriers[2], carriers[3]])
    record: dict[str, Any] = codec.serialize(score.document)

    decoded: ScoreDocument = codec.deserialize(as_stored(record))

    assert codec.serialize(decoded) == record
    assert _relation_layout(document=decoded) == _relation_layout(document=score.document)
