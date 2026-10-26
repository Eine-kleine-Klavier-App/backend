from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument, ScoreEntity
from piano_app.domain.score.document.models.material import Carrier, Note, NoteCarrier
from piano_app.domain.score.document.models.notation import Accidental, GracePlacement
from piano_app.domain.score.document.models.structural import Staff
from piano_app.domain.score.document.models.structural.rhythm import (
    GraceItem,
    LeafRhythmicContainer,
)
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.compiler.intents import (
    AddGraceCarrierNoteIntent,
    AddGraceNoteIntent,
    ChangeGraceTypeIntent,
    ChangeGraceValueIntent,
    RemoveGraceNoteIntent,
)
from piano_app.domain.score.document.services.mutation.compiler.steps import (
    expect_entity,
    resolve_entities,
)
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
    MutationRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.intent import (
    AddGraceNoteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    CreateNoteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    UpdateGraceTypeRequest,
    UpdateGraceValueRequest,
)
from piano_app.domain.score.document.services.pitch import PitchResolutionError, SignCell
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch


def _accidental_in_force(
    *,
    document: ScoreDocument,
    staff: Staff,
    leaf: LeafRhythmicContainer,
    staff_step: int,
    placement: GracePlacement,
) -> Accidental:
    """The accidental a grace note gets when none is written: the one in force at its host's
    point, read up to the cell of its group's place."""
    geometry: ScoreGeometry = ScoreGeometry(document=document)
    try:
        return ScorePitch(
            document=document,
            geometry=geometry,
            contexts=ContextIndex(document=document, geometry=geometry),
        ).accidental_at(
            staff=staff,
            point=geometry.point_of(anchor=leaf.anchor),
            staff_step=staff_step,
            cell=SignCell.BEFORE if placement is GracePlacement.BEFORE else SignCell.AFTER,
        )
    except (ValueError, PitchResolutionError) as error:
        raise MutationRejectedError(reason=str(error)) from error


class AddGraceNoteCompiler:
    """Compiles a grace note into one request: its group, item, carrier and note are made where
    the request is analyzed. The grace notes belong to the note of the carrier named, a note or a
    rest (a rest may give its time in theory)."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: AddGraceNoteIntent,
    ) -> Sequence[MutationRequest]:
        entity_ids: tuple[str, ...] = (intent.host_carrier_id, intent.staff_id)
        if intent.after_carrier_id is not None:
            entity_ids = (*entity_ids, intent.after_carrier_id)

        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document,
            entity_ids=entity_ids,
        )
        host: Carrier = expect_entity(
            entities_by_id=entities_by_id, entity_id=intent.host_carrier_id, expected=Carrier
        )
        staff: Staff = expect_entity(
            entities_by_id=entities_by_id, entity_id=intent.staff_id, expected=Staff
        )
        leaf = host.owner
        if not isinstance(leaf, LeafRhythmicContainer):
            raise MutationRejectedError(
                "Grace notes belong to a note of a leaf, not to a grace note."
            )

        after: GraceItem | None = None
        if intent.after_carrier_id is not None:
            after_carrier: Carrier = expect_entity(
                entities_by_id=entities_by_id,
                entity_id=intent.after_carrier_id,
                expected=Carrier,
            )
            owner = after_carrier.owner
            if (
                not isinstance(owner, GraceItem)
                or owner.grace_group.leaf is not leaf
                or owner.grace_group.placement is not intent.placement
            ):
                raise MutationRejectedError(
                    "The carrier is not a grace carrier of this note at this place."
                )

            after = owner

        accidental: Accidental = (
            intent.accidental
            if intent.accidental is not None
            else _accidental_in_force(
                document=document,
                staff=staff,
                leaf=leaf,
                staff_step=intent.staff_step,
                placement=intent.placement,
            )
        )

        return [
            AddGraceNoteRequest(
                leaf=leaf,
                placement=intent.placement,
                grace_type=intent.grace_type,
                written_value=intent.written_value,
                staff=staff,
                staff_step=intent.staff_step,
                accidental=accidental,
                fingering=intent.fingering,
                after=after,
            )
        ]


class AddGraceCarrierNoteCompiler:
    """Compiles a note joining a grace carrier into one note creation in that carrier; the
    carrier keeps its item, so its place and its time do not change."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: AddGraceCarrierNoteIntent,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document,
            entity_ids=(intent.carrier_id, intent.staff_id),
        )
        carrier: NoteCarrier = expect_entity(
            entities_by_id=entities_by_id, entity_id=intent.carrier_id, expected=NoteCarrier
        )
        staff: Staff = expect_entity(
            entities_by_id=entities_by_id, entity_id=intent.staff_id, expected=Staff
        )
        item = carrier.owner
        if not isinstance(item, GraceItem):
            raise MutationRejectedError("The carrier is not a grace carrier.")

        group = item.grace_group
        accidental: Accidental = (
            intent.accidental
            if intent.accidental is not None
            else _accidental_in_force(
                document=document,
                staff=staff,
                leaf=group.leaf,
                staff_step=intent.staff_step,
                placement=group.placement,
            )
        )
        return [
            CreateNoteRequest(
                carrier=carrier,
                staff=staff,
                staff_step=intent.staff_step,
                accidental=accidental,
                fingering=intent.fingering,
            )
        ]


class RemoveGraceNoteCompiler:
    """Compiles removing a grace note into one delete: the note alone when its carrier is a chord
    that keeps others, else its item, else the whole group when it was the last one."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: RemoveGraceNoteIntent,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document, entity_ids=(intent.note_id,)
        )
        note: Note = expect_entity(
            entities_by_id=entities_by_id, entity_id=intent.note_id, expected=Note
        )
        item = note.note_carrier.owner
        if not isinstance(item, GraceItem):
            raise MutationRejectedError("The note is not a grace note.")

        if len(note.note_carrier.notes) > 1:
            return [DeleteRequest(target=note)]

        group = item.grace_group
        return [DeleteRequest(target=group if len(group.grace_items) == 1 else item)]


class ChangeGraceTypeCompiler:
    """Compiles setting the kind of a grace note's group into one update of that group."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: ChangeGraceTypeIntent,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document, entity_ids=(intent.note_id,)
        )
        note: Note = expect_entity(
            entities_by_id=entities_by_id, entity_id=intent.note_id, expected=Note
        )
        item = note.note_carrier.owner
        if not isinstance(item, GraceItem):
            raise MutationRejectedError("The note is not a grace note.")

        return [UpdateGraceTypeRequest(target=item.grace_group, grace_type=intent.grace_type)]


class ChangeGraceValueCompiler:
    """Compiles writing a grace carrier as another value into one update of its item."""

    def compile(
        self,
        *,
        document: ScoreDocument,
        intent: ChangeGraceValueIntent,
    ) -> Sequence[MutationRequest]:
        entities_by_id: dict[str, ScoreEntity] = resolve_entities(
            document=document, entity_ids=(intent.carrier_id,)
        )
        carrier: Carrier = expect_entity(
            entities_by_id=entities_by_id, entity_id=intent.carrier_id, expected=Carrier
        )
        item = carrier.owner
        if not isinstance(item, GraceItem):
            raise MutationRejectedError("The carrier is not a grace carrier.")

        return [UpdateGraceValueRequest(target=item, rhythmic_value=intent.written_value)]
