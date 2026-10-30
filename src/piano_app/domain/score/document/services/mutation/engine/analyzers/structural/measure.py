from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.structural import Measure
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.actions.structural import (
    CreateMeasureAction,
    DeleteMeasureAction,
    UpdateMeasureTimeSignatureAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.structural import (
    CreateEmptyMeasureRequest,
    DeleteEmptyMeasureRequest,
    UpdateMeasureTimeSignatureRequest,
)


class CreateEmptyMeasureAnalyzer:
    """Adds an empty measure of a given time signature before a given measure, or after
    the last one.

    Nothing around it is split: whoever adds a measure this way has decided what crosses its
    barline — a time-signature change fills it with what moves into it.
    """

    def analyze(
        self,
        *,
        request: CreateEmptyMeasureRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        before: Measure | None = request.before

        if before is not None and before not in request.document.measures:
            raise ValueError("A measure is inserted before a measure of its document.")

        yield CreateMeasureAction(
            document=request.document,
            before=before,
            time_signature=request.time_signature,
        )


class DeleteEmptyMeasureAnalyzer:
    """Removes a measure that holds no anchor.

    The last remaining measure is refused. An anchor still in it is a broken invariant:
    whoever removes a measure this way has moved everything out of it first.
    """

    def analyze(
        self,
        *,
        request: DeleteEmptyMeasureRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        measure: Measure = request.target
        document: ScoreDocument = request.document

        if measure not in document.measures:
            raise ValueError("A removed measure must be in its document.")

        if len(document.measures) == 1:
            raise MutationRejectedError("The last remaining measure cannot be removed.")

        if measure.anchors:
            raise ValueError(
                "A removed empty measure still holds anchors: they must be moved out of it first."
            )

        yield DeleteMeasureAction(target=measure, document=document)


class UpdateMeasureTimeSignatureAnalyzer:
    """Gives a measure another time signature, keeping the measure and its anchors.

    An anchor at or past the new end is a broken order, not a choice: whoever shortens a
    measure moves its anchors inside the new length first (the measure refuses it too).
    The same signature writes nothing.
    """

    def analyze(
        self,
        *,
        request: UpdateMeasureTimeSignatureRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        measure: Measure = request.target

        if measure.time_signature == request.time_signature:
            return

        if any(
            anchor.position.value >= request.time_signature.fraction for anchor in measure.anchors
        ):
            raise ValueError(
                "A measure is shortened while an anchor lies past its new end: it must be "
                "moved inside first."
            )

        yield UpdateMeasureTimeSignatureAction(
            target=measure,
            time_signature=request.time_signature,
        )
