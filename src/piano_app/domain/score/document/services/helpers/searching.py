from piano_app.domain.score.document.models.context.scope.staff import StaffScoped
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    Staff,
    TemporalAnchor,
)
from piano_app.domain.score.document.models.structural.rhythm import (
    RhythmicContainer,
    RhythmicContainerParent,
)

# Slot lookup: what already sits at a given place in the model. Purely a question
# about occupancy, not about coordinates -- anything that needs to measure, project
# or compare positions belongs in `services/geometry` instead.


def find_anchor_at(
    *,
    measure: Measure,
    position: MeasurePosition,
) -> TemporalAnchor | None:
    # one or None guaranteed in model
    return next(
        (anchor for anchor in measure.anchors if anchor.position == position),
        None,
    )


def find_container_at(
    *,
    measure: Measure,
    position: MeasurePosition,
    scope: RhythmicContainerParent,
) -> RhythmicContainer | None:
    """The container — a leaf or a group — starting at this slot in this scope.

    Nested containers starting at the same instant share the anchor but live in different
    scopes, so only a direct child of the scope counts; within one scope siblings never
    overlap, so there is at most one.
    """
    anchor: TemporalAnchor | None = find_anchor_at(measure=measure, position=position)
    if anchor is None:
        return None

    containers: list[RhythmicContainer] = [
        container for container in anchor.containers if container.parent is scope
    ]
    if len(containers) > 1:
        raise ValueError(f"Multiple containers start at one anchor in scope {scope}.")

    return containers[0] if containers else None


def find_staff_point_context_at[T: StaffScoped](
    *,
    anchor: TemporalAnchor,
    context_type: type[T],
    staff: Staff,
) -> T | None:
    """The context of exactly ``context_type`` already starting at this anchor, for
    this staff — the search behind the one-per-anchor-per-staff invariant. Shared by
    every staff-scoped point-context creator so the invariant is enforced once, not
    reimplemented per type.
    """
    return next(
        (
            context
            for context in anchor.starting_contexts
            if isinstance(context, context_type) and context.staff is staff
        ),
        None,
    )
