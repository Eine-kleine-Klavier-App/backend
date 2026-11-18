from fractions import Fraction

import pytest
from tests.unit.domain.document_builders import anchor

from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import NewFragment, Refrain, Volta


def _document() -> ScoreDocument:
    return ScoreDocument.create_fresh(voice_count=1, staff_count=1, measure_count=7)


def _restored[T: (Refrain, Volta)](*, document: ScoreDocument, kind: type[T]) -> dict[str, T]:
    return {
        context.id: context
        for measure in document.measures
        for a in measure.anchors
        for context in a.starting_contexts
        if isinstance(context, kind)
    }


@pytest.mark.unit
def test_refrains_survive_a_round_trip_one_closed_one_lasting_until_the_end() -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    document: ScoreDocument = _document()
    closed = Refrain.create(
        start=anchor(document, Fraction(0)), end=anchor(document, Fraction(2)), times=3
    )
    open_ended = Refrain.create(start=anchor(document, Fraction(3)), end=None, times=2)

    decoded: ScoreDocument = codec.deserialize(codec.serialize(document))

    restored: dict[str, Refrain] = _restored(document=decoded, kind=Refrain)
    assert restored[closed.id].times == 3
    assert restored[closed.id].end is not None
    assert restored[closed.id].jump.id == closed.jump.id
    assert restored[open_ended.id].end is None
    assert restored[open_ended.id].jump.source is None
    assert restored[closed.id].jump in restored[closed.id].start.arriving_jumps
    assert codec.serialize(decoded) == codec.serialize(document)


@pytest.mark.unit
def test_a_volta_survives_a_round_trip_with_its_jumps_and_passes() -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    document: ScoreDocument = _document()
    volta: Volta = Volta.create(
        start=anchor(document, Fraction(0)),
        body_end=anchor(document, Fraction(2)),
        fragments=[
            NewFragment(end=anchor(document, Fraction(3)), passes=frozenset({1, 3})),
            NewFragment(end=anchor(document, Fraction(4)), passes=frozenset({2})),
        ],
    )

    decoded: ScoreDocument = codec.deserialize(codec.serialize(document))

    restored: Volta = _restored(document=decoded, kind=Volta)[volta.id]
    assert restored.pass_count == 4
    assert [fragment.passes for fragment in restored.fragments] == [
        frozenset({1, 3}),
        frozenset({2}),
    ]
    assert [rule.jump.id for rule in restored.rules] == [rule.jump.id for rule in volta.rules]
    assert all(
        rule.jump in rule.jump.target.arriving_jumps for rule in restored.rules if rule.jump.target
    )
    assert codec.serialize(decoded) == codec.serialize(document)


@pytest.mark.unit
def test_a_volta_whose_last_ending_lasts_to_the_end_of_the_score_survives_a_round_trip() -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    document: ScoreDocument = _document()
    volta: Volta = Volta.create(
        start=anchor(document, Fraction(0)),
        body_end=anchor(document, Fraction(2)),
        fragments=[
            NewFragment(end=anchor(document, Fraction(3)), passes=frozenset({1})),
            NewFragment(end=None, passes=frozenset({2})),
        ],
    )

    decoded: ScoreDocument = codec.deserialize(codec.serialize(document))

    restored: Volta = _restored(document=decoded, kind=Volta)[volta.id]
    assert restored.fragments[-1].end is None
    assert codec.serialize(decoded) == codec.serialize(document)
