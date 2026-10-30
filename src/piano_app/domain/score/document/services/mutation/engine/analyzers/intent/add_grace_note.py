from piano_app.domain.score.document.models.material import NoteCarrier
from piano_app.domain.score.document.models.notation import GracePlacement
from piano_app.domain.score.document.models.structural.rhythm import GraceGroup, GraceItem
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.analyzers.base import expect_sent
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.requests.intent import (
    AddGraceNoteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    CreateNoteCarrierRequest,
    CreateNoteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    CreateGraceGroupRequest,
    CreateGraceItemRequest,
)


class AddGraceNoteAnalyzer:
    """Adds a grace note to its group, after the item the request names and first when it names
    none: the group when there is none, then the item, its carrier and the note. A group has one
    type, refused otherwise; whether the time they take fits the note they belong to is decided
    where the item is made."""

    def analyze(
        self,
        *,
        request: AddGraceNoteRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        group: GraceGroup | None = (
            request.leaf.grace_before
            if request.placement is GracePlacement.BEFORE
            else request.leaf.grace_after
        )
        if group is None:
            group = expect_sent(
                sent=(
                    yield CreateGraceGroupRequest(
                        leaf=request.leaf,
                        grace_type=request.grace_type,
                        placement=request.placement,
                    )
                ),
                expected=GraceGroup,
            )
        elif group.grace_type is not request.grace_type:
            raise MutationRejectedError("The grace notes of one group are all of one kind.")

        index: int = 0
        if request.after is not None:
            if request.after not in group.grace_items:
                raise ValueError("The grace item to stand after is not in the group.")

            index = group.grace_items.index(request.after) + 1

        item: GraceItem = expect_sent(
            sent=(
                yield CreateGraceItemRequest(
                    group=group, rhythmic_value=request.written_value, index=index
                )
            ),
            expected=GraceItem,
        )
        carrier: NoteCarrier = expect_sent(
            sent=(yield CreateNoteCarrierRequest(owner=item)),
            expected=NoteCarrier,
        )
        yield CreateNoteRequest(
            carrier=carrier,
            staff=request.staff,
            staff_step=request.staff_step,
            accidental=request.accidental,
            fingering=request.fingering,
        )
