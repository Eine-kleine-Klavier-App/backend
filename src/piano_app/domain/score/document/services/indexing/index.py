from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.context import Context
from piano_app.domain.score.document.models.material import Note
from piano_app.domain.score.document.models.structural import Staff, TemporalAnchor
from piano_app.domain.score.document.models.structural.rhythm import (
    GroupRhythmicContainer,
    LeafRhythmicContainer,
    RhythmicContainer,
    RhythmicContainerParent,
)


class Index:
    """Something derived from the model that has to learn of a change to stay right.

    The ten events are what a change of the model can mean to an index; an index overrides
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

    def invalidate_child(self, *, scope: RhythmicContainerParent, child: RhythmicContainer) -> None:
        """A child was attached to or detached from the scope."""

    def invalidate_staff(self, *, staff: Staff) -> None:
        """A pitch context on the staff was created, removed, changed or moved."""

    def invalidate_note(self, *, note: Note) -> None:
        """A note was created, deleted, moved to another step or staff, or given another
        accidental."""

    def invalidate_context(self, *, context: Context) -> None:
        """A context of any kind was created, removed, moved, had an end moved or, on voices,
        had its voices changed."""

    def attach_entity(self, *, owner: object, entity: ScoreEntity) -> None:
        """The owner took the entity as its own: put it in a list or a field that holds it."""

    def detach_entity(self, *, owner: object, entity: ScoreEntity) -> None:
        """The owner let the entity go: took it out of a list or a field that held it."""
