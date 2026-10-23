from piano_app.domain.score.document.models.context import Context
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.structural import Staff, TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainerParent,
)


class Index:
    """Something derived from the model that has to learn of a change to stay right.

    The eight events are what a change of the model can mean to an index; an index overrides
    the ones it answers for and leaves the rest. Each is delivered after the change, so a
    detached entity still holds the place it was detached from, and only marks what went
    stale: the next read rebuilds it.
    """

    def invalidate_measures(self) -> None:
        """A measure was created or deleted, or its time signature changed."""

    def invalidate_anchor(self, *, anchor: TemporalAnchor) -> None:
        """An anchor was created, deleted or moved."""

    def invalidate_leaf(self, *, leaf: LeafRhythmicContainer) -> None:
        """A leaf was created, deleted or resized."""

    def invalidate_group(self, *, group: GroupRhythmicContainer) -> None:
        """A group was created, deleted, resized or split."""

    def invalidate_scope(self, *, scope: RhythmicContainerParent) -> None:
        """A child was attached to or detached from the scope."""

    def invalidate_staff(self, *, staff: Staff) -> None:
        """A pitch context on the staff was created, removed, changed or moved."""

    def invalidate_note(self, *, note: Note) -> None:
        """A note was created, deleted, moved to another step or staff, or given another
        accidental."""

    def invalidate_context(self, *, context: Context) -> None:
        """A context of any kind was created, removed, moved, had an end moved or, on voices,
        had its voices changed."""
