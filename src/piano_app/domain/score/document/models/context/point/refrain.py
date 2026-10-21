from dataclasses import dataclass
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.score.document.models.structural.jump import Jump

from .base import PointContext
from .jump_rule import JumpRule

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.structural import TemporalAnchor


def _check_times(*, times: int) -> None:
    if times < 2:
        raise ValueError("A refrain is played at least twice.")


@dataclass(kw_only=True, eq=False)
class Refrain(PointContext):
    """A stretch of the score played ``times`` times: ``|: 1 2 :|`` played three times.

    ``start`` is where the stretch begins; its end is where the jump back leaves from, a
    barline or the end of the score. The jump is the refrain's own: it is taken at each
    arrival at the end but the last, so on arrivals one to ``times`` minus one. Score-scoped
    — no scope mixin."""

    _jump: Jump
    _times: int

    @property
    def jump(self) -> Jump:
        return self._jump

    @property
    def times(self) -> int:
        return self._times

    @property
    def rules(self) -> tuple[JumpRule, ...]:
        return (JumpRule(jump=self._jump, arrivals=frozenset(range(1, self._times))),)

    @property
    def end(self) -> TemporalAnchor | None:
        return self._jump.source

    def fires_on(self, *, arrival: int) -> bool:
        """Whether the jump back is taken on the given arrival at the end of the stretch,
        counted from one."""
        return 1 <= arrival < self._times

    def _check_invariants(self) -> None:
        super()._check_invariants()
        _check_times(times=self._times)

        if self._jump.target is not self.start:
            raise ValueError("A refrain's jump must land at the place the refrain starts.")

        end: TemporalAnchor | None = self._jump.source
        if end is not None and not self.start.precedes(end):
            raise ValueError("A refrain must end after it starts.")

    def validate(self) -> None:
        """Check the invariants again against the barlines as they are now; they may have been
        broken by a change of the score around the refrain."""
        self._check_invariants()

    def attach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        super().attach(sink=sink)
        self._jump.attach(sink=sink)

    def detach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        self._jump.detach(sink=sink)
        super().detach(sink=sink)

    def set_times(self, *, times: int, sink: MutationSink = DIRECT_SINK) -> None:
        """Change how many times the stretch is played, keeping the refrain itself."""
        _check_times(times=times)
        sink.set_field(self, "_times", times)

    def set_end(self, *, end: TemporalAnchor | None, sink: MutationSink = DIRECT_SINK) -> None:
        """Move the end of the stretch to another barline, or to the end of the score
        (``None``), keeping the refrain itself."""
        if end is not None and not self.start.precedes(end):
            raise ValueError("A refrain must end after it starts.")

        self._jump.set_source(source=end, sink=sink)

    def set_start(self, *, start: TemporalAnchor, sink: MutationSink = DIRECT_SINK) -> None:
        end: TemporalAnchor | None = self._jump.source
        if end is not None and not start.precedes(end):
            raise ValueError("A refrain must end after it starts.")

        self._jump.set_target(target=start, sink=sink)
        super().set_start(start=start, sink=sink)

    @classmethod
    def create(
        cls,
        *,
        start: TemporalAnchor,
        end: TemporalAnchor | None,
        times: int,
        sink: MutationSink = DIRECT_SINK,
    ) -> Refrain:
        jump: Jump = Jump.unattached(source=end, target=start)
        refrain = cls(_start=start, _jump=jump, _times=times)

        refrain.attach(sink=sink)
        return refrain

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        start: TemporalAnchor,
        jump: Jump,
        times: int,
        sink: MutationSink = DIRECT_SINK,
    ) -> Refrain:
        refrain = cls(id=id, _start=start, _jump=jump, _times=times)

        refrain.attach(sink=sink)
        return refrain
