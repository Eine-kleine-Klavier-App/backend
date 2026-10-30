from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.models.structural import Measure
from piano_app.domain.score.document.services.mutation.instructions.actions.structural import (
    CreateMeasureAction,
    DeleteMeasureAction,
    UpdateMeasureTimeSignatureAction,
)


class CreateMeasureHandler:
    """Creates a measure and links it into the document's chain at its place."""

    def handle(
        self,
        *,
        action: CreateMeasureAction,
        sink: MutationSink,
    ) -> Measure:
        measure: Measure = Measure.create(time_signature=action.time_signature)

        if action.before is None:
            action.document.append_measure(measure=measure, sink=sink)
        else:
            action.document.insert_measure_before(
                measure=measure,
                before=action.before,
                sink=sink,
            )

        return measure


class DeleteMeasureHandler:
    """Unlinks a measure from the document's chain."""

    def handle(
        self,
        *,
        action: DeleteMeasureAction,
        sink: MutationSink,
    ) -> None:
        action.document.remove_measure(measure=action.target, sink=sink)
        return None


class UpdateMeasureTimeSignatureHandler:
    """Gives a measure another time signature."""

    def handle(
        self,
        *,
        action: UpdateMeasureTimeSignatureAction,
        sink: MutationSink,
    ) -> None:
        action.target.set_time_signature(time_signature=action.time_signature, sink=sink)
        return None
