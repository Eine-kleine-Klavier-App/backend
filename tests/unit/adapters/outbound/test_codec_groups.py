from fractions import Fraction

import pytest
from tests.fixtures.records import as_stored

from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.notation import RhythmicValue
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
)

from ...domain.scene import Score, build_score, group, layout, note, quarters, size

# Groups start at their own anchor, so the codec stores each group's anchor and restores
# it before the group's children. Compared structurally: a decoded entity keeps its id,
# so entity equality would hold even if every other field decoded wrong.


def _score_with_groups() -> Score:
    """A plain measure, then a measure with a triplet holding a nested triplet at its start (all
    three sharing one anchor) and a quarter triplet crossing into a third measure."""
    score: Score = build_score(measure_count=3)
    quarters(score=score, measure=0)

    outer: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(1),
        written=size(RhythmicValue.EIGHTH, count=3),
        occupied=size(RhythmicValue.QUARTER),
    )
    inner: GroupRhythmicContainer = group(
        score=score,
        parent=outer,
        at=Fraction(1),
        written=size(RhythmicValue.SIXTEENTH, count=3),
        occupied=size(RhythmicValue.EIGHTH),
    )
    for index in range(3):
        note(
            score=score,
            parent=inner,
            at=1 + Fraction(index, 36),
            rhythmic_value=RhythmicValue.SIXTEENTH,
            step=index + 1,
        )
    for index in (1, 2):
        note(
            score=score,
            parent=outer,
            at=1 + Fraction(index, 12),
            rhythmic_value=RhythmicValue.EIGHTH,
            step=4,
        )
    quarters(score=score, measure=1, beats=(1, 2))

    crossing: GroupRhythmicContainer = group(
        score=score,
        parent=score.voice,
        at=Fraction(7, 4),
        written=size(RhythmicValue.QUARTER, count=3),
        occupied=size(RhythmicValue.HALF),
    )
    for index in range(3):
        note(
            score=score,
            parent=crossing,
            at=Fraction(7, 4) + Fraction(index, 6),
            rhythmic_value=RhythmicValue.QUARTER,
            step=5,
        )
    quarters(score=score, measure=2, beats=(1, 2, 3))

    return score


def _as_score(*, document: ScoreDocument) -> Score:
    return Score(
        document=document,
        voice=document.voices[0],
        staff=document.staffs[0],
        measures=list(document.measures),
    )


@pytest.mark.unit
def test_a_document_with_nested_and_barline_crossing_groups_round_trips() -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    score: Score = _score_with_groups()

    decoded: ScoreDocument = codec.deserialize(as_stored(codec.serialize(score.document)))

    assert codec.serialize(decoded) == codec.serialize(score.document)
    assert layout(score=_as_score(document=decoded)) == layout(score=score)


@pytest.mark.unit
def test_a_decoded_group_starts_at_its_own_decoded_anchor() -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    score: Score = _score_with_groups()

    decoded: Score = _as_score(document=codec.deserialize(codec.serialize(score.document)))

    outer = decoded.voice.children[4]
    assert isinstance(outer, GroupRhythmicContainer)
    assert outer.start_anchor.measure is decoded.measures[1]
    assert outer.start_anchor in decoded.measures[1].anchors
    assert outer in outer.start_anchor.containers
    assert len(outer.start_anchor.containers) == 3


@pytest.mark.unit
def test_beam_end_offsets_survive_codec_roundtrip() -> None:
    from piano_app.domain.score.document.models.presentation import (
        EndpointOffsets,
        PresentationTarget,
    )
    from piano_app.domain.score.document.services.helpers import find_beams, iter_leaves

    from ...domain.mutation.scenarios.test_intent_split_beam import _line

    score, _, beam = _line(4)
    score.document.presentation.set_endpoints(
        target=PresentationTarget(entity_id=beam.id), value=EndpointOffsets(left=-1.5, right=2.25)
    )
    codec = ScoreDocumentCodec()
    decoded = codec.deserialize(codec.serialize(score.document))
    carriers = [leaf.carrier for leaf in iter_leaves(decoded.voices[0]) if leaf.carrier is not None]
    restored = find_beams(carriers=carriers)[0]
    assert restored.id == beam.id
    assert decoded.presentation.endpoints == score.document.presentation.endpoints
