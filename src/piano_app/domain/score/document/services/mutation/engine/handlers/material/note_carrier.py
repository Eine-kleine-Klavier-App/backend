from piano_app.domain.score.document.models.material import CarrierOwner, NoteCarrier
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.services.mutation.instructions.actions.material import (
    CreateNoteCarrierAction,
    DeleteNoteCarrierAction,
    UpdateArticulationAction,
    UpdateOrnamentAction,
)


class CreateNoteCarrierHandler:
    """Creates a note carrier on its owner."""

    def handle(
        self,
        *,
        action: CreateNoteCarrierAction,
        sink: MutationSink,
    ) -> NoteCarrier:
        owner: CarrierOwner = action.owner
        carrier: NoteCarrier = NoteCarrier.create(
            owner=owner,
            articulations=action.articulations,
            ornament=action.ornament,
            sink=sink,
        )
        return carrier


class DeleteNoteCarrierHandler:
    """Detaches a note carrier from its owner."""

    def handle(
        self,
        *,
        action: DeleteNoteCarrierAction,
        sink: MutationSink,
    ) -> None:
        note_carrier: NoteCarrier = action.target
        note_carrier.detach(sink=sink)
        return None


class UpdateArticulationHandler:
    """Sets the marks of articulation a note carrier has."""

    def handle(
        self,
        *,
        action: UpdateArticulationAction,
        sink: MutationSink,
    ) -> None:
        note_carrier: NoteCarrier = action.target
        note_carrier.set_articulations(articulations=action.articulations, sink=sink)
        return None


class UpdateOrnamentHandler:
    """Sets a note carrier's ornament."""

    def handle(
        self,
        *,
        action: UpdateOrnamentAction,
        sink: MutationSink,
    ) -> None:
        note_carrier: NoteCarrier = action.target
        note_carrier.set_ornament(ornament=action.ornament, sink=sink)
        return None
