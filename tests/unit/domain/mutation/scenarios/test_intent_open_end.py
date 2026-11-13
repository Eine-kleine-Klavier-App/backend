from fractions import Fraction

import pytest
from tests.unit.domain.document_builders import anchor, note, score

from piano_app.application.use_cases.score.shared.view import ScoreView
from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import Slur
from piano_app.domain.score.document.models.structural import MEASURE_START
from piano_app.domain.score.document.services.contexts import ContextIndex, covered_by
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import (
    AppendMeasureIntent,
    EditIntent,
    OpenContextEndIntent,
    PitchEditMode,
)
from piano_app.domain.score.document.services.mutation.engine.log import MutationLog
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError


def _run(*, document: ScoreDocument, intent: EditIntent) -> MutationLog:
    return build_engine().process(
        document=document,
        requests=build_compiler().compile(document=document, intent=intent),
    )


def _slur(*, document: ScoreDocument) -> Slur:
    return Slur.create(
        start=anchor(document, Fraction(1, 2)),
        end=anchor(document, Fraction(2)),
        voices=[document.voices[0]],
    )


def _open(*, document: ScoreDocument, slur: Slur) -> MutationLog:
    return _run(
        document=document,
        intent=OpenContextEndIntent(context_id=slur.id, mode=PitchEditMode.PRESERVE_PITCH),
    )


def test_a_span_made_to_last_until_the_end_has_no_end_anchor_and_covers_the_rest() -> None:
    document: ScoreDocument = score()
    slur: Slur = _slur(document=document)
    last: Fraction = Fraction(5, 2)
    note(document, last)

    log: MutationLog = _open(document=document, slur=slur)

    assert slur.end is None
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    assert geometry.end_of(context=slur).value == geometry.root.extent
    assert any(
        carrier.id
        for carrier in covered_by(
            context=slur,
            document=document,
            geometry=geometry,
            contexts=ContextIndex(document=document, geometry=geometry),
        ).carriers
    )

    log.rollback()
    assert slur.end is not None
    assert slur in slur.end.ending_contexts


def test_a_span_that_already_lasts_until_the_end_cannot_be_opened_again() -> None:
    document: ScoreDocument = score()
    slur: Slur = _slur(document=document)
    _open(document=document, slur=slur)

    with pytest.raises(MutationRejectedError, match="already lasts"):
        _open(document=document, slur=slur)


def test_a_measure_added_at_the_end_does_not_swallow_a_span_that_lasted_until_the_end() -> None:
    document: ScoreDocument = score()
    slur: Slur = _slur(document=document)
    _open(document=document, slur=slur)
    measures_before: int = len(document.measures)

    log: MutationLog = _run(document=document, intent=AppendMeasureIntent())

    assert len(document.measures) == measures_before + 1
    assert slur.end is not None
    assert slur.end.measure is document.measures[-1]
    assert slur.end.position == MEASURE_START

    log.rollback()
    assert slur.end is None
    assert len(document.measures) == measures_before


def test_a_span_with_no_end_is_written_without_one() -> None:
    document: ScoreDocument = score()
    slur: Slur = _slur(document=document)
    _open(document=document, slur=slur)

    view = ScoreView(document=document).jsonify()

    context = next(item for item in view["contexts"] if item["id"] == slur.id)  # type: ignore[attr-defined,index,union-attr]
    assert context["end_measure_id"] is None
    assert context["end_position"] is None
