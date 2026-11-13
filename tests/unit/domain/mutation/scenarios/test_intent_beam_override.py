from math import inf, nan

import pytest

from piano_app.domain.score.document.models.presentation import EndpointOffsets, PresentationTarget
from piano_app.domain.score.document.services.helpers import find_beams
from piano_app.domain.score.document.services.mutation.compiler.intents.update.split_beam import (
    SplitBeamIntent,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.presentation import (
    PresentationEditor,
    SetEndpointOffsets,
)

from ...scene import apply_intent, snapshot
from .test_intent_split_beam import _line


def _apply(*, score, command):
    log = MutationLog()
    PresentationEditor().apply(document=score.document, commands=[command], sink=log)
    return log


@pytest.mark.unit
def test_offsets_are_one_reversible_edit_without_changing_music() -> None:
    score, members, beam = _line(4)
    before = snapshot(score=score)
    override = EndpointOffsets(left=0.75, right=1.5)
    log = _apply(
        score=score,
        command=SetEndpointOffsets(target=PresentationTarget(entity_id=beam.id), value=override),
    )
    assert (
        score.document.presentation.endpoints.get(PresentationTarget(entity_id=beam.id)) == override
    )
    assert snapshot(score=score) == before
    assert list(beam.members) == members
    log.rollback()
    assert score.document.presentation.endpoints.get(PresentationTarget(entity_id=beam.id)) is None
    log.reapply()
    assert (
        score.document.presentation.endpoints.get(PresentationTarget(entity_id=beam.id)) == override
    )
    reset = _apply(
        score=score,
        command=SetEndpointOffsets(target=PresentationTarget(entity_id=beam.id), value=None),
    )
    assert score.document.presentation.endpoints.get(PresentationTarget(entity_id=beam.id)) is None
    reset.rollback()
    assert (
        score.document.presentation.endpoints.get(PresentationTarget(entity_id=beam.id)) == override
    )


@pytest.mark.unit
@pytest.mark.parametrize("value", [inf, -inf, nan])
@pytest.mark.parametrize("side", ["left", "right"])
def test_nonfinite_offsets_are_refused(value: float, side: str) -> None:
    with pytest.raises(ValueError, match="finite"):
        EndpointOffsets(**{side: value})


@pytest.mark.unit
def test_only_an_existing_beam_can_be_edited() -> None:
    score, members, beam = _line(4)
    for entity_id in ("missing", members[0].id):
        with pytest.raises(ValueError):
            _apply(
                score=score,
                command=SetEndpointOffsets(
                    target=PresentationTarget(entity_id=entity_id), value=None
                ),
            )
    assert score.document.presentation.endpoints.get(PresentationTarget(entity_id=beam.id)) is None


@pytest.mark.unit
def test_split_keeps_override_only_on_surviving_relation_and_undo_restores() -> None:
    score, members, beam = _line(4)
    override = EndpointOffsets(left=0.5, right=1.5)
    score.document.presentation.set_endpoints(
        target=PresentationTarget(entity_id=beam.id), value=override
    )
    log = apply_intent(
        score=score, intent=SplitBeamIntent(beam_id=beam.id, before_carrier_id=members[2].id)
    )
    found = find_beams(carriers=members)
    assert len(found) == 2
    assert (
        found[0] is beam
        and score.document.presentation.endpoints.get(PresentationTarget(entity_id=found[0].id))
        == override
    )
    assert (
        score.document.presentation.endpoints.get(PresentationTarget(entity_id=found[1].id)) is None
    )
    log.rollback()
    assert (
        list(beam.members) == members
        and score.document.presentation.endpoints.get(PresentationTarget(entity_id=beam.id))
        == override
    )
