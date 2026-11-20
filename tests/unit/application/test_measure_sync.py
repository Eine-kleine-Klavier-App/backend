import asyncio
from fractions import Fraction

import pytest
from tests.fixtures.drafts import in_memory_history
from tests.unit.domain.scene import Score, build_score, note_at, quarters

from piano_app.application.ports.score import VersionedDraftDocument
from piano_app.application.use_cases.score.edit.service import ScoreEditService
from piano_app.application.use_cases.score.shared import (
    MeasureSync,
    ScoreState,
    ScoreView,
    state_sync,
)
from piano_app.domain.score.document.models.notation import Fingering
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import SetFingeringIntent

# A client is sent a score whole once, then only the measures each edit changes, with the
# versions it goes from and to.


def _score() -> Score:
    score: Score = build_score(measure_count=3)
    for measure in range(3):
        quarters(score=score, measure=measure)

    return score


def _service(*, score: Score) -> tuple[ScoreEditService, VersionedDraftDocument]:
    history = in_memory_history()
    draft: VersionedDraftDocument = asyncio.run(
        history.create(title="sync", author_id="owner", ref_score_id=None, document=score.document)
    )

    return ScoreEditService(
        engine=build_engine(), compiler=build_compiler(), history=history
    ), draft


def _finger(*, service: ScoreEditService, draft_id: str, note_id: str) -> ScoreState:
    return asyncio.run(
        service.apply(
            draft_id=draft_id,
            actor_id="owner",
            intent=SetFingeringIntent(note_id=note_id, fingering=Fingering.THUMB),
        )
    )


@pytest.mark.unit
def test_a_score_loaded_as_it_is_is_sent_whole() -> None:
    score: Score = _score()

    sync: MeasureSync = state_sync(
        state=ScoreState(
            document=score.document, view=ScoreView(document=score.document), version=4, step=None
        )
    )

    assert (sync.from_version, sync.to_version) == (None, 4)
    assert sync.header is not None
    assert [share["measure"]["id"] for share in sync.measures] == [
        measure.id for measure in score.document.measures
    ]
    assert [sounds.measure_id for sounds in sync.sounds] == [
        measure.id for measure in score.document.measures
    ]
    assert sync.timing is not None
    assert sync.sound_error is None


@pytest.mark.unit
def test_an_edit_is_sent_as_the_measure_it_changed_and_an_undo_as_the_same() -> None:
    score: Score = _score()
    service, draft = _service(score=score)
    second = score.document.measures[1].id

    edited: MeasureSync = state_sync(
        state=_finger(
            service=service,
            draft_id=draft.draft_id,
            note_id=note_at(score=score, at=Fraction(5, 4)).id,
        )
    )
    undone: MeasureSync = state_sync(
        state=asyncio.run(service.undo(draft_id=draft.draft_id, actor_id="owner"))
    )

    for sync, versions in ((edited, (0, 1)), (undone, (1, 2))):
        assert (sync.from_version, sync.to_version) == versions
        assert [share["measure"]["id"] for share in sync.measures] == [second]
        assert [sounds.measure_id for sounds in sync.sounds] == [second]
        assert sync.timing is None
        assert sync.removed == ()


@pytest.mark.unit
def test_an_edit_sends_what_a_fresh_load_of_the_score_has_in_that_measure() -> None:
    score: Score = _score()
    service, draft = _service(score=score)

    state: ScoreState = _finger(
        service=service, draft_id=draft.draft_id, note_id=note_at(score=score, at=Fraction(5, 4)).id
    )
    sent: MeasureSync = state_sync(state=state)
    fresh: MeasureSync = state_sync(
        state=ScoreState(
            document=state.document, view=ScoreView(document=state.document), version=1, step=None
        )
    )

    (share,) = sent.measures
    (sounds,) = sent.sounds
    assert share in fresh.measures
    assert sounds in fresh.sounds


@pytest.mark.unit
def test_an_undo_with_nothing_to_undo_sends_nothing() -> None:
    service, draft = _service(score=_score())

    sync: MeasureSync = state_sync(
        state=asyncio.run(service.undo(draft_id=draft.draft_id, actor_id="owner"))
    )

    assert (sync.from_version, sync.to_version) == (0, 0)
    assert (sync.header, sync.measures, sync.sounds, sync.removed) == (None, (), (), ())
