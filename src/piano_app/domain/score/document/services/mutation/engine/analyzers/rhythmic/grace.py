from collections.abc import Sequence
from fractions import Fraction

from piano_app.domain.score.document.models.notation import GracePlacement, GraceType
from piano_app.domain.score.document.models.structural.rhythm import GraceGroup, GraceItem
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import SLASHED_SCALE, fits, sounding_of
from piano_app.domain.score.document.services.mutation.engine.typing import MutationAnalysis
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError
from piano_app.domain.score.document.services.mutation.instructions.actions.rhythmic import (
    CreateGraceGroupAction,
    CreateGraceItemAction,
    UpdateGraceTypeAction,
    UpdateGraceValueAction,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    Deletable,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    CreateGraceGroupRequest,
    CreateGraceItemRequest,
    UpdateGraceTypeRequest,
    UpdateGraceValueRequest,
)


class CreateGraceGroupAnalyzer:
    """Creates the group of grace notes before or after a leaf's note; a leaf has at most one at
    each place, refused here before anything is created."""

    def analyze(
        self,
        *,
        request: CreateGraceGroupRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        existing: GraceGroup | None = (
            request.leaf.grace_before
            if request.placement is GracePlacement.BEFORE
            else request.leaf.grace_after
        )
        if existing is not None:
            raise MutationRejectedError(f"The note already has grace notes {request.placement}.")

        yield CreateGraceGroupAction(
            leaf=request.leaf, grace_type=request.grace_type, placement=request.placement
        )


class CreateGraceItemAnalyzer:
    """Adds a grace item to a group. A grace note has no time of its own: it borrows it from the
    note it is attached to, and that note must keep some of its own (the groups before and after
    it count together), refused here before anything is created."""

    def analyze(
        self,
        *,
        request: CreateGraceItemRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        leaf = request.group.leaf
        taken: Fraction = sounding_of(group=request.group, written=request.rhythmic_value.fraction)
        if not fits(leaf=leaf, length=leaf.occupied_size.fraction, extra=taken):
            raise MutationRejectedError(
                "The grace notes would take all the time of the note they belong to."
            )

        yield CreateGraceItemAction(
            group=request.group, rhythmic_value=request.rhythmic_value, index=request.index
        )


def cascade_grace_item(*, target: GraceItem) -> Sequence[Deletable]:
    """Decides the grace item's deletion cascade: its carrier goes first, and with it its notes."""
    return [] if target.carrier is None else [target.carrier]  # type: ignore[list-item]


def cascade_grace_group(*, target: GraceGroup) -> Sequence[Deletable]:
    """Decides the group's deletion cascade: its items, in order."""
    return list(target.grace_items)


class UpdateGraceTypeAnalyzer:
    """Sets the kind of a group of grace notes. A slashed group sounds a quarter of what it is
    written, a plain one as written, so the change moves the time the group takes from its
    note, and the note must still keep some of its own, refused here before anything changes."""

    def analyze(
        self,
        *,
        request: UpdateGraceTypeRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        group: GraceGroup = request.target
        written: Fraction = sum(
            (item.rhythmic_value.fraction for item in group.grace_items), Fraction(0)
        )
        then: Fraction = (
            written * SLASHED_SCALE if request.grace_type is GraceType.ACCIACCATURA else written
        )
        change: Fraction = then - sounding_of(group=group, written=written)
        if not fits(leaf=group.leaf, length=group.leaf.occupied_size.fraction, extra=change):
            raise MutationRejectedError(
                "The grace notes would take all the time of the note they belong to."
            )

        yield UpdateGraceTypeAction(target=group, grace_type=request.grace_type)


class UpdateGraceValueAnalyzer:
    """Writes a grace item as another value. The time its group takes from the note moves by what
    the item now sounds against what it sounded, and the note must still keep some of its own,
    refused here before anything changes."""

    def analyze(
        self,
        *,
        request: UpdateGraceValueRequest,
        geometry: ScoreGeometry,
    ) -> MutationAnalysis:
        item: GraceItem = request.target
        group: GraceGroup = item.grace_group
        change: Fraction = sounding_of(
            group=group, written=request.rhythmic_value.fraction
        ) - sounding_of(group=group, written=item.rhythmic_value.fraction)
        if not fits(leaf=group.leaf, length=group.leaf.occupied_size.fraction, extra=change):
            raise MutationRejectedError(
                "The grace notes would take all the time of the note they belong to."
            )

        yield UpdateGraceValueAction(target=item, rhythmic_value=request.rhythmic_value)
