from fractions import Fraction

import pytest
from tests.unit.domain.document_builders import anchor

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import Refrain
from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.guards import JumpElementsGuard
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError


def _document() -> ScoreDocument:
    return ScoreDocument.create_fresh(voice_count=1, staff_count=1, measure_count=5)


def _refrain(*, document: ScoreDocument, first: int, last: int) -> Refrain:
    return Refrain.create(
        start=anchor(document, Fraction(first)),
        end=anchor(document, Fraction(last)),
        times=2,
    )


def _check(*, document: ScoreDocument) -> None:
    JumpElementsGuard().search_fixes(document=document, geometry=ScoreGeometry(document=document))


@pytest.mark.unit
def test_the_guard_lets_sound_elements_pass() -> None:
    document: ScoreDocument = _document()
    _refrain(document=document, first=0, last=4)
    _refrain(document=document, first=1, last=2)

    _check(document=document)


@pytest.mark.unit
def test_the_guard_refuses_an_element_whose_invariants_no_longer_hold() -> None:
    document: ScoreDocument = _document()
    refrain: Refrain = _refrain(document=document, first=0, last=2)
    DIRECT_SINK.set_field(refrain, "_times", 1)

    with pytest.raises(MutationRejectedError, match="at least twice"):
        _check(document=document)


@pytest.mark.unit
def test_the_guard_refuses_elements_that_lie_partly_over_each_other() -> None:
    document: ScoreDocument = _document()
    _refrain(document=document, first=0, last=2)
    _refrain(document=document, first=1, last=3)

    with pytest.raises(MutationRejectedError, match="partly over"):
        _check(document=document)
