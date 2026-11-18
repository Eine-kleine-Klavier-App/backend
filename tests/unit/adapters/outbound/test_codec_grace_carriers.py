import json
from fractions import Fraction

import pytest
from tests.fixtures.records import as_stored

from piano_app.adapters.outbound.shared.codec import ScoreDocumentCodec
from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    GracePlacement,
    GraceType,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceGroup,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.helpers import iter_leaves
from piano_app.domain.score.document.services.mutation.compiler import (
    AddGraceCarrierNoteIntent,
    AddGraceNoteIntent,
)

from ...domain.scene import Score, apply_intent, build_score, insert_note

# The carrier of a grace item, and the notes on it, are stored with the rest of the document.


def _host(*, document: ScoreDocument) -> LeafRhythmicContainer:
    return next(iter(iter_leaves(document.voices[0])))


def _grace(*, score: Score, placement: GracePlacement, step: int, after: str | None = None) -> None:
    host: LeafRhythmicContainer = _host(document=score.document)
    assert host.carrier is not None
    apply_intent(
        score=score,
        intent=AddGraceNoteIntent(
            host_carrier_id=host.carrier.id,
            placement=placement,
            grace_type=GraceType.APPOGGIATURA,
            written_value=DottedRhythmicValue(value=RhythmicValue.SIXTEENTH),
            staff_id=score.staff.id,
            staff_step=step,
            accidental=Accidental.NATURAL,
            after_carrier_id=after,
        ),
    )


def _steps(*, group: GraceGroup | None) -> list[list[int]]:
    assert group is not None
    steps: list[list[int]] = []
    for item in group.grace_items:
        carrier = item.carrier
        assert isinstance(carrier, NoteCarrier)
        steps.append(sorted(note.staff_step for note in carrier.notes))

    return steps


@pytest.mark.unit
def test_grace_notes_before_and_after_a_note_survive_a_round_trip() -> None:
    codec: ScoreDocumentCodec = ScoreDocumentCodec()
    score: Score = build_score(measure_count=1)
    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER, step=2)
    _grace(score=score, placement=GracePlacement.BEFORE, step=3)
    before: GraceGroup | None = _host(document=score.document).grace_before
    assert before is not None
    first = before.grace_items[0].carrier
    assert first is not None
    _grace(score=score, placement=GracePlacement.BEFORE, step=4, after=first.id)
    _grace(score=score, placement=GracePlacement.AFTER, step=1)
    apply_intent(
        score=score,
        intent=AddGraceCarrierNoteIntent(
            carrier_id=first.id,
            staff_id=score.staff.id,
            staff_step=5,
            accidental=Accidental.NATURAL,
        ),
    )

    encoded: str = json.dumps(codec.serialize(score.document))
    decoded: ScoreDocument = codec.deserialize(as_stored(codec.serialize(score.document)))

    host: LeafRhythmicContainer = _host(document=decoded)
    assert _steps(group=host.grace_before) == [[3, 5], [4]]
    assert _steps(group=host.grace_after) == [[1]]
    assert json.dumps(codec.serialize(decoded)) == encoded
