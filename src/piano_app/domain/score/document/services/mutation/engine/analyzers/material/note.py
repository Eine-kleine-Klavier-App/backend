from piano_app.domain.score.document.models.material import Carrier, Note, NoteCarrier
from piano_app.domain.score.document.models.structural.rhythm import (
    LeafRhythmicContainer,
    RhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.helpers import find_container_at
from piano_app.domain.score.document.services.mutation.engine.buffer import EmitBuffer
from piano_app.domain.score.document.services.mutation.engine.resolver import ResolveBound
from piano_app.domain.score.document.services.mutation.instructions import Bound, ResultRef
from piano_app.domain.score.document.services.mutation.instructions.actions.material import (
    CreateNoteAction,
    DeleteNoteAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    CreateNoteCarrierRequest,
    CreateNoteRequest,
    DeleteNoteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    DeleteRelationRequest,
)


class CreateNoteAnalyzer:
    """Decides where to create a note in the requested scope slot.

    A same-size leaf with a note carrier triggers a chord join; every other slot
    state delegates creation of a suitable carrier.
    """

    def analyze(
        self,
        *,
        request: CreateNoteRequest,
        resolver: ResolveBound,
    ) -> EmitBuffer:
        buffer: EmitBuffer = EmitBuffer(request=request)
        # the scope may be a group created earlier in the same gesture
        scope: RhythmicContainerParent = resolver(request.scope)

        # only a leaf of the scope can be reused; a group starting there is a sibling the
        # new leaf will displace
        container: RhythmicContainer | None = find_container_at(
            measure=request.measure,
            position=request.position,
            scope=scope,
        )
        leaf: LeafRhythmicContainer | None = (
            container if isinstance(container, LeafRhythmicContainer) else None
        )
        carrier: Carrier | None = leaf.carrier if leaf is not None else None

        # chord-join only when the slot already holds a same-size note carrier;
        # everything else (rest carrier, different size, no leaf) is the carrier's call
        note_carrier: Bound[NoteCarrier]
        if (
            leaf is not None
            and leaf.written_size.value == request.written_value
            and leaf.written_size.count == 1
            and isinstance(carrier, NoteCarrier)
        ):
            # TODO:
            #   PITCH-VALIDATION (deferred — pitch is not in v1): when the carrier already
            #   holds a note at the SAME pitch, chord-duplicate is forbidden → reject (or
            #   replace); cross-voice unison stays allowed. See [[pitch-and-voice-policy]].
            #   No-op until pitch lands.
            note_carrier = carrier
        else:
            note_carrier = ResultRef[NoteCarrier]()
            buffer.incorporate(
                item=CreateNoteCarrierRequest(
                    scope=scope,
                    measure=request.measure,
                    position=request.position,
                    written_value=request.written_value,
                    out=note_carrier,
                ),
            )

        buffer.incorporate(
            item=CreateNoteAction(
                note_carrier=note_carrier,
                staff=request.staff,
                staff_step=request.staff_step,
                accidental=request.accidental,
                fingering=request.fingering,
                out=request.out,
            ),
        )

        return buffer


class DeleteNoteAnalyzer:
    """Decides the note's deletion cascade.

    Note-to-note relations are deleted before the note. Cleanup of an empty
    carrier is deferred to the mutation boundary.
    """

    def analyze(
        self,
        *,
        request: DeleteNoteRequest,
        resolver: ResolveBound,
    ) -> EmitBuffer:
        buffer: EmitBuffer = EmitBuffer(request=request)
        note: Note = request.target

        for note_relation in note.relations:
            buffer.incorporate(item=DeleteRelationRequest(target=note_relation))

        buffer.incorporate(item=DeleteNoteAction(target=note))

        return buffer
