import json
from collections.abc import Callable
from dataclasses import fields
from fractions import Fraction

import pytest
from tests.fixtures.records import as_stored

from piano_app.adapters.outbound.shared.codec import CodecError, ScoreDocumentCodec
from piano_app.application.ports.score import DocumentRecord
from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.context import (
    ClefChange,
    Context,
    DynamicChange,
    Hairpin,
    KeySignatureChange,
    OctaveTransposition,
    Slur,
    SustainHold,
    TempoChange,
    TempoTransition,
)
from piano_app.domain.score.document.models.notation import (
    Accidental,
    Clef,
    DottedRhythmicValue,
    DynamicMarking,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural import TemporalAnchor

from ...domain.scene import Score, anchor_at, build_two_voices, quarters

# One tempo, a clef and a key signature for the staff, and one dynamic shared by both voices.
_START_CONTEXTS: int = 4

# Contexts are stored in one table, and each anchor lists the ids of the ones that start at it,
# in order. Re-serialising
# only proves the stored fields survive; the back-references (staff, voice and anchor indexes)
# are not in the record, so they are checked on the decoded document directly.


def _scene() -> tuple[Score, Score]:
    """Two voices on one staff over two measures, the first voice filled with quarters."""
    first, second = build_two_voices(measure_count=2)
    quarters(score=first, measure=0)
    quarters(score=first, measure=1)
    return first, second


def _fields(*, context: Context) -> dict[str, object]:
    """Every dataclass field of a context, with linked entities named by id."""
    described: dict[str, object] = {"type": type(context).__name__}
    for field in fields(context):
        field_value: object = getattr(context, field.name)
        if isinstance(field_value, ScoreEntity):
            described[field.name] = field_value.id
        elif isinstance(field_value, list):
            described[field.name] = [
                entity.id for entity in field_value if isinstance(entity, ScoreEntity)
            ]
        else:
            described[field.name] = field_value

    return described


def _contexts(*, document: ScoreDocument) -> dict[str, Context]:
    by_id: dict[str, Context] = {}
    for measure in document.measures:
        for anchor in measure.anchors:
            for context in anchor.starting_contexts:
                by_id[context.id] = context

    return by_id


def _anchor(*, document: ScoreDocument, anchor_id: str) -> TemporalAnchor:
    for measure in document.measures:
        for anchor in measure.anchors:
            if anchor.id == anchor_id:
                return anchor

    raise LookupError(anchor_id)


def _ids(entities: object) -> list[str]:
    assert isinstance(entities, (list, tuple))
    return [entity.id for entity in entities if isinstance(entity, ScoreEntity)]


_QUARTER: DottedRhythmicValue = DottedRhythmicValue(value=RhythmicValue.QUARTER)


def _tempo_with_a_label(first: Score, second: Score) -> Context:
    return TempoChange.create(
        start=anchor_at(score=first, at=Fraction(1, 4)),
        beat=DottedRhythmicValue(value=RhythmicValue.EIGHTH, dots_count=1),
        bpm=96,
        show_label=True,
    )


def _tempo_without_a_label(first: Score, second: Score) -> Context:
    return TempoChange.create(
        start=anchor_at(score=first, at=Fraction(1, 2)), beat=_QUARTER, bpm=120
    )


def _tempo_transition(first: Score, second: Score) -> Context:
    return TempoTransition.create(
        start=anchor_at(score=first, at=Fraction(1, 4)),
        end=anchor_at(score=first, at=Fraction(5, 4)),
        ratio=Fraction(7, 9),
    )


def _clef_with_octave_transposition(first: Score, second: Score) -> Context:
    return ClefChange.create(
        start=anchor_at(score=first, at=Fraction(5, 4)),
        staff=first.staff,
        clef=Clef.BASS,
        octave_transposition=-1,
    )


def _key_signature(first: Score, second: Score) -> Context:
    return KeySignatureChange.create(
        start=anchor_at(score=first, at=Fraction(1)),
        staff=first.staff,
        alterations=(
            Accidental.NATURAL,
            Accidental.FLAT,
            *(Accidental.NATURAL,) * 2,
            Accidental.FLAT,
            *(Accidental.NATURAL,) * 2,
        ),
    )


def _dynamic_on_both_voices(first: Score, second: Score) -> Context:
    return DynamicChange.create(
        start=anchor_at(score=first, at=Fraction(1, 2)),
        voices=[second.voice, first.voice],
        dynamic=DynamicMarking.MEZZO_PIANO,
    )


def _sustain_across_measures(first: Score, second: Score) -> Context:
    return SustainHold.create(
        start=anchor_at(score=first, at=Fraction(1, 4)),
        end=anchor_at(score=first, at=Fraction(3, 2)),
    )


def _octave_transposition_across_measures(first: Score, second: Score) -> Context:
    return OctaveTransposition.create(
        start=anchor_at(score=first, at=Fraction(3, 4)),
        end=anchor_at(score=first, at=Fraction(7, 4)),
        staff=first.staff,
        octaves=-2,
    )


def _hairpin_across_measures(first: Score, second: Score) -> Context:
    return Hairpin.create(
        start=anchor_at(score=first, at=Fraction(1, 2)),
        end=anchor_at(score=first, at=Fraction(5, 4)),
        voices=[first.voice, second.voice],
        steps=-2,
    )


def _slur_on_one_voice(first: Score, second: Score) -> Context:
    return Slur.create(
        start=anchor_at(score=first, at=Fraction(0)),
        end=anchor_at(score=first, at=Fraction(3, 4)),
        voices=[first.voice],
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "make_context",
    [
        _tempo_with_a_label,
        _tempo_without_a_label,
        _tempo_transition,
        _clef_with_octave_transposition,
        _key_signature,
        _dynamic_on_both_voices,
        _sustain_across_measures,
        _octave_transposition_across_measures,
        _hairpin_across_measures,
        _slur_on_one_voice,
    ],
    ids=[
        "tempo-score-with-label",
        "tempo-score-without-label",
        "tempo-transition-score-span",
        "clef-staff",
        "key-signature-staff",
        "dynamic-voices",
        "sustain-score-span",
        "octave-transposition-staff-span",
        "hairpin-voices-span",
        "slur-voices-span",
    ],
)
def test_each_context_kind_survives_a_round_trip(
    make_context: Callable[[Score, Score], Context],
) -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    first, second = _scene()
    context: Context = make_context(first, second)

    encoded: str = json.dumps(codec.serialize(first.document))
    decoded: ScoreDocument = codec.deserialize(json.loads(encoded))

    decoded_context: Context = _contexts(document=decoded)[context.id]
    assert _fields(context=decoded_context) == _fields(context=context)
    assert decoded_context in decoded_context.start.starting_contexts
    assert json.dumps(codec.serialize(decoded)) == encoded


@pytest.mark.unit
def test_several_contexts_on_one_anchor_keep_every_index_order() -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    first, second = _scene()
    start: TemporalAnchor = anchor_at(score=first, at=Fraction(1))
    end: TemporalAnchor = anchor_at(score=first, at=Fraction(3, 2))
    earlier_end: TemporalAnchor = anchor_at(score=first, at=Fraction(1, 2))
    Slur.create(start=anchor_at(score=first, at=Fraction(0)), end=end, voices=[first.voice])
    ClefChange.create(start=start, staff=first.staff, clef=Clef.TREBLE)
    KeySignatureChange.create(
        start=start,
        staff=first.staff,
        alterations=(*(Accidental.NATURAL,) * 4, Accidental.SHARP, *(Accidental.NATURAL,) * 2),
    )
    TempoChange.create(start=start, beat=_QUARTER, bpm=72)
    DynamicChange.create(
        start=start, voices=[first.voice, second.voice], dynamic=DynamicMarking.FORTE
    )
    Hairpin.create(start=start, end=end, voices=[first.voice], steps=2)
    OctaveTransposition.create(start=start, end=end, staff=first.staff, octaves=1)
    Hairpin.create(
        start=anchor_at(score=first, at=Fraction(0)),
        end=earlier_end,
        voices=[second.voice],
        steps=-1,
    )

    encoded: str = json.dumps(codec.serialize(first.document))
    decoded: ScoreDocument = codec.deserialize(as_stored(json.loads(encoded)))

    decoded_start: TemporalAnchor = _anchor(document=decoded, anchor_id=start.id)
    decoded_end: TemporalAnchor = _anchor(document=decoded, anchor_id=end.id)
    assert _ids(decoded_start.starting_contexts) == _ids(start.starting_contexts)
    assert _ids(decoded_end.ending_contexts) == _ids(end.ending_contexts)
    assert _ids(decoded.staffs[0].contexts) == _ids(first.staff.contexts)
    assert _ids(decoded.voices[0].contexts) == _ids(first.voice.contexts)
    assert _ids(decoded.voices[1].contexts) == _ids(second.voice.contexts)
    assert json.dumps(codec.serialize(decoded)) == encoded


@pytest.mark.unit
def test_a_document_with_contexts_re_serialises_byte_for_byte_twice() -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    first, second = _scene()
    for make_context in (
        _tempo_with_a_label,
        _key_signature,
        _sustain_across_measures,
        _octave_transposition_across_measures,
        _hairpin_across_measures,
        _dynamic_on_both_voices,
    ):
        make_context(first, second)

    encoded: str = json.dumps(codec.serialize(first.document))
    once: ScoreDocument = codec.deserialize(json.loads(encoded))
    twice: ScoreDocument = codec.deserialize(codec.serialize(once))

    assert json.dumps(codec.serialize(once)) == encoded
    assert json.dumps(codec.serialize(twice)) == encoded
    assert len(json.loads(encoded)["tables"]["contexts"]) == _START_CONTEXTS + 6


def _serialized_contexts(score: Score) -> list[dict[str, object]]:
    return list(ScoreDocumentCodec().serialize(score.document)["tables"]["contexts"].values())


@pytest.mark.unit
def test_a_scene_holds_the_contexts_every_score_starts_with() -> None:
    first, _ = _scene()

    assert len(_serialized_contexts(first)) == _START_CONTEXTS
    assert first.document.missing_initial_contexts() == []


def _without_contexts(record: DocumentRecord, *, kind: str | None) -> DocumentRecord:
    """The record with the contexts of a kind (all of them for ``None``) taken out of both the
    contexts table and the lists of the anchors they start at."""
    contexts: dict[str, dict[str, object]] = record["tables"]["contexts"]
    removed: set[str] = {
        context_id for context_id, row in contexts.items() if kind is None or row["kind"] == kind
    }
    return {
        **record,
        "tables": {
            **record["tables"],
            "contexts": {
                context_id: row for context_id, row in contexts.items() if context_id not in removed
            },
            "anchors": {
                anchor_id: {
                    **row,
                    "context_ids": [
                        context_id for context_id in row["context_ids"] if context_id not in removed
                    ],
                }
                for anchor_id, row in record["tables"]["anchors"].items()
            },
        },
    }


@pytest.mark.unit
def test_a_record_without_the_start_of_score_contexts_is_refused() -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    first, _ = _scene()
    record: DocumentRecord = codec.serialize(first.document)

    with pytest.raises(CodecError, match="tempo"):
        codec.deserialize(_without_contexts(record, kind="tempo_change"))

    with pytest.raises(CodecError, match="lacks"):
        codec.deserialize(_without_contexts(record, kind=None))
