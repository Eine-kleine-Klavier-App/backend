from dataclasses import dataclass
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.base import ScoreEntity
from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink

if TYPE_CHECKING:
    from .temporal_anchor import TemporalAnchor


def _check_places(*, source: TemporalAnchor | None, target: TemporalAnchor | None) -> None:
    if source is None and target is None:
        raise ValueError("A jump leaves from or lands at a barline: not both are the score's end.")

    if source is target:
        raise ValueError("A jump leaves one place and lands at another.")


@dataclass(kw_only=True, eq=False)
class Jump(ScoreEntity):
    """A jump from one place of the score to another: ``source`` is the barline it leaves
    from and ``target`` the barline it lands at, in either order on the timeline. ``None``
    stands for the end of the score, which has no barline of its own (a repeat closing the
    piece leaves from there), but not for both ends at once.

    It has no kind and no count: going back or forward only follows from which of the two
    comes first, and on which arrival at ``source`` it is taken is kept by the element built
    from it (a repeat, a volta). Each end that is a barline lists the jump."""

    _source: TemporalAnchor | None
    _target: TemporalAnchor | None

    @property
    def source(self) -> TemporalAnchor | None:
        return self._source

    @property
    def target(self) -> TemporalAnchor | None:
        return self._target

    def _check_invariants(self) -> None:
        super()._check_invariants()
        _check_places(source=self._source, target=self._target)

    def attach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        if self._source is not None:
            self._source.add_departing_jump(jump=self, sink=sink)

        if self._target is not None:
            self._target.add_arriving_jump(jump=self, sink=sink)

    def detach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        if self._source is not None:
            self._source.remove_departing_jump(jump=self, sink=sink)

        if self._target is not None:
            self._target.remove_arriving_jump(jump=self, sink=sink)

    def set_source(
        self,
        *,
        source: TemporalAnchor | None,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        """Make the jump leave from another barline (or from the end of the score), keeping
        the jump itself."""
        _check_places(source=source, target=self._target)

        self.detach(sink=sink)
        sink.set_field(self, "_source", source)
        self.attach(sink=sink)

    def set_target(
        self,
        *,
        target: TemporalAnchor | None,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        """Make the jump land at another barline (or at the end of the score), keeping the
        jump itself."""
        _check_places(source=self._source, target=target)

        self.detach(sink=sink)
        sink.set_field(self, "_target", target)
        self.attach(sink=sink)

    @classmethod
    def unattached(
        cls,
        *,
        source: TemporalAnchor | None,
        target: TemporalAnchor | None,
    ) -> Jump:
        """A jump no barline lists yet: the element that owns it attaches it together with
        itself, so nothing is left listed if the element refuses to be built."""
        return cls(_source=source, _target=target)

    @classmethod
    def create(
        cls,
        *,
        source: TemporalAnchor | None,
        target: TemporalAnchor | None,
        sink: MutationSink = DIRECT_SINK,
    ) -> Jump:
        jump = cls.unattached(source=source, target=target)

        jump.attach(sink=sink)
        return jump

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        source: TemporalAnchor | None,
        target: TemporalAnchor | None,
        sink: MutationSink = DIRECT_SINK,
    ) -> Jump:
        jump = cls(id=id, _source=source, _target=target)

        jump.attach(sink=sink)
        return jump
