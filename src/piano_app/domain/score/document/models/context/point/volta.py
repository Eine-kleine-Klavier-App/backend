from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.score.document.models.structural.jump import Jump

from .base import PointContext
from .jump_rule import JumpRule

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.structural import TemporalAnchor


@dataclass(frozen=True, slots=True, kw_only=True)
class VoltaFragment:
    """One fragment of a volta as read from its jumps: where it starts and ends (``None``:
    the end of the score) and the passes it is played in."""

    start: TemporalAnchor
    end: TemporalAnchor | None
    passes: frozenset[int]


@dataclass(frozen=True, slots=True, kw_only=True)
class NewFragment:
    """A fragment to build a volta from: where it ends and the passes it is played in. It
    starts where the one before it ends, the first where the body of the volta ends."""

    end: TemporalAnchor | None
    passes: frozenset[int]


def _body_end_of(*, skips: Sequence[JumpRule]) -> TemporalAnchor:
    if not skips:
        raise ValueError("A volta has at least one fragment.")

    body_end: TemporalAnchor | None = skips[0].jump.source
    if body_end is None:
        raise ValueError("A volta's jumps forward leave from the barline its body ends at.")

    return body_end


def _pass_count_of(*, skips: Sequence[JumpRule]) -> int:
    """The number of passes: the one the derived last fragment is played in, which the last
    jump forward is taken on."""
    arrivals: frozenset[int] = skips[-1].arrivals
    if len(arrivals) != 1:
        raise ValueError("The last jump forward of a volta is taken on exactly one pass.")

    (pass_count,) = arrivals
    return pass_count


def _fragment_passes(
    *,
    backs: Sequence[JumpRule],
    skips: Sequence[JumpRule],
) -> list[frozenset[int]]:
    """The passes of every fragment: those of the later ones are the arrivals of the jumps
    forward to them, and the first fragment is played in every other pass before the last."""
    later: list[frozenset[int]] = [skip.arrivals for skip in skips[: len(backs) - 1]]
    taken: frozenset[int] = frozenset().union(*later)
    first: frozenset[int] = frozenset(range(1, _pass_count_of(skips=skips))) - taken

    return [first, *later]


def check_fragment_passes(*, passes: Sequence[frozenset[int]]) -> None:
    """The passes of the fragments to build a volta from, in order: each fragment has some,
    together they hold every pass from the first, each in one fragment, the first pass is the
    first fragment's, and each fragment is first played in a later pass than the one before."""
    if not passes:
        raise ValueError("A volta has at least one fragment.")

    if any(not fragment_passes for fragment_passes in passes):
        raise ValueError("A fragment of a volta is played in at least one pass.")

    total: int = sum(len(fragment_passes) for fragment_passes in passes)
    union: frozenset[int] = frozenset().union(*passes)
    if union != frozenset(range(1, total + 1)):
        raise ValueError(
            "The fragments of a volta together hold every pass from the first, each in one."
        )

    if 1 not in passes[0]:
        raise ValueError(
            "A fragment names only passes after the first and before the last one: "
            "the first pass belongs to the first fragment."
        )

    firsts: list[int] = [min(fragment_passes) for fragment_passes in passes]
    if any(after <= before for before, after in pairwise(firsts)):
        raise ValueError("Each fragment is first played in a later pass than the one before.")


def _check_fragment_ends(
    *,
    body_end: TemporalAnchor,
    backs: Sequence[JumpRule],
    skips: Sequence[JumpRule],
) -> None:
    ends: list[TemporalAnchor | None] = [back.jump.source for back in backs]
    previous: TemporalAnchor = body_end
    for index, end in enumerate(ends):
        if end is None:
            if index != len(ends) - 1:
                raise ValueError("Only the last fragment of a volta lasts to the end of the score.")

            continue

        if not previous.precedes(end):
            raise ValueError("A fragment of a volta must end after it starts.")

        previous = end

    # the jumps forward land where the fragments end: at the start of the next fragment, and
    # for the last of them just past the last stored one
    if any(skip.jump.target is not end for skip, end in zip(skips, ends, strict=True)):
        raise ValueError("A volta's jumps forward land at the ends of its fragments.")


def _check_passes(*, backs: Sequence[JumpRule], skips: Sequence[JumpRule]) -> None:
    pass_count: int = _pass_count_of(skips=skips)
    later: list[frozenset[int]] = [skip.arrivals for skip in skips[:-1]]
    if pass_count < 2:
        raise ValueError("A volta is played at least twice.")

    if any(not passes for passes in later):
        raise ValueError("A fragment of a volta is played in at least one pass.")

    if any(not passes <= frozenset(range(2, pass_count)) for passes in later):
        raise ValueError("A fragment names only passes after the first and before the last one.")

    if len(frozenset().union(*later)) != sum(len(passes) for passes in later):
        raise ValueError("A pass belongs to one fragment of a volta only.")

    passes_of_fragments: list[frozenset[int]] = _fragment_passes(backs=backs, skips=skips)
    firsts: list[int] = [min(passes) for passes in passes_of_fragments]
    if any(after <= before for before, after in pairwise(firsts)):
        raise ValueError("Each fragment is first played in a later pass than the one before.")

    for back, passes in zip(backs, passes_of_fragments, strict=True):
        if back.arrivals != frozenset(range(1, len(passes) + 1)):
            raise ValueError("A volta jumps back at every arrival at the end of a fragment.")


def _check_shape(
    *,
    start: TemporalAnchor,
    backs: Sequence[JumpRule],
    skips: Sequence[JumpRule],
) -> None:
    """Whether the jumps make a volta that starts at ``start``: they are all there, they leave
    from and land at the places a volta's do, and their arrivals give consistent passes."""
    if not backs or len(backs) != len(skips):
        raise ValueError("A volta has a jump back and a jump forward for each fragment.")

    body_end: TemporalAnchor = _body_end_of(skips=skips)
    if not start.precedes(body_end):
        raise ValueError("The body of a volta must end after it starts.")

    if any(skip.jump.source is not body_end for skip in skips):
        raise ValueError("A volta's jumps forward all leave from the end of its body.")

    if any(back.jump.target is not start for back in backs):
        raise ValueError("A volta's jumps back all land at the place it starts.")

    _check_fragment_ends(body_end=body_end, backs=backs, skips=skips)
    _check_passes(backs=backs, skips=skips)


def _build_jumps(
    *,
    start: TemporalAnchor,
    body_end: TemporalAnchor,
    fragments: Sequence[NewFragment],
) -> tuple[tuple[JumpRule, ...], tuple[JumpRule, ...]]:
    """The jumps back and the jumps forward of a volta of these fragments; the last pass is
    the one after all the fragments' passes."""
    check_fragment_passes(passes=[fragment.passes for fragment in fragments])

    pass_count: int = 1 + sum(len(fragment.passes) for fragment in fragments)
    backs: tuple[JumpRule, ...] = tuple(
        JumpRule(
            jump=Jump.unattached(source=fragment.end, target=start),
            arrivals=frozenset(range(1, len(fragment.passes) + 1)),
        )
        for fragment in fragments
    )
    skips: tuple[JumpRule, ...] = (
        *(
            JumpRule(
                jump=Jump.unattached(source=body_end, target=before.end),
                arrivals=after.passes,
            )
            for before, after in pairwise(fragments)
        ),
        JumpRule(
            jump=Jump.unattached(source=body_end, target=fragments[-1].end),
            arrivals=frozenset({pass_count}),
        ),
    )

    return backs, skips


@dataclass(kw_only=True, eq=False)
class Volta(PointContext):
    """The endings of a repeat, one element for all its fragments: ``|: 1 | [1. 2 :| [2. 3``.

    ``start`` is where the body begins, the part played in every pass. Each fragment after
    the body is played in its own passes and ends with a jump back to the start; the passes
    left over by the stored fragments belong to the first one, and the last pass, which is
    not stored as a fragment, goes on after the last stored one. The element holds only
    jumps, each with the arrivals it is taken on: a jump back from the end of every
    fragment, and from the end of the body a jump forward to every later fragment and one
    past the last, taken on the last pass. The passes of the fragments and their number
    are read from those. Score-scoped — no scope mixin."""

    _backs: tuple[JumpRule, ...]
    _skips: tuple[JumpRule, ...]

    @property
    def backs(self) -> tuple[JumpRule, ...]:
        return self._backs

    @property
    def skips(self) -> tuple[JumpRule, ...]:
        return self._skips

    @property
    def rules(self) -> tuple[JumpRule, ...]:
        return (*self._backs, *self._skips)

    @property
    def body_end(self) -> TemporalAnchor:
        return _body_end_of(skips=self._skips)

    @property
    def pass_count(self) -> int:
        return _pass_count_of(skips=self._skips)

    @property
    def fragments(self) -> tuple[VoltaFragment, ...]:
        passes: list[frozenset[int]] = _fragment_passes(backs=self._backs, skips=self._skips)
        fragments: list[VoltaFragment] = []
        start: TemporalAnchor = self.body_end
        for back, fragment_passes in zip(self._backs, passes, strict=True):
            end: TemporalAnchor | None = back.jump.source
            fragments.append(VoltaFragment(start=start, end=end, passes=fragment_passes))
            if end is not None:
                start = end

        return tuple(fragments)

    def _check_invariants(self) -> None:
        super()._check_invariants()
        _check_shape(start=self.start, backs=self._backs, skips=self._skips)

    def validate(self) -> None:
        """Check the invariants again against the barlines as they are now; they may have been
        broken by a change of the score around the volta."""
        self._check_invariants()

    def reshape(
        self,
        *,
        start: TemporalAnchor,
        body_end: TemporalAnchor,
        fragments: Sequence[NewFragment],
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        """Give the volta another body and other fragments, keeping the volta itself. What is
        refused is refused before anything changes."""
        backs, skips = _build_jumps(start=start, body_end=body_end, fragments=fragments)
        _check_shape(start=start, backs=backs, skips=skips)

        self.detach(sink=sink)
        sink.set_field(self, "_start", start)
        sink.set_field(self, "_backs", backs)
        sink.set_field(self, "_skips", skips)
        self.attach(sink=sink)

    def attach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        super().attach(sink=sink)
        for entry in (*self._backs, *self._skips):
            entry.jump.attach(sink=sink)

    def detach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        for entry in (*self._backs, *self._skips):
            entry.jump.detach(sink=sink)

        super().detach(sink=sink)

    @classmethod
    def create(
        cls,
        *,
        start: TemporalAnchor,
        body_end: TemporalAnchor,
        fragments: Sequence[NewFragment],
        sink: MutationSink = DIRECT_SINK,
    ) -> Volta:
        """A volta of the fragments in order; together they hold every pass from the first
        to the one before the last, each in one fragment. The last pass is the one after
        them all, and the jumps are built from these."""
        backs, skips = _build_jumps(start=start, body_end=body_end, fragments=fragments)
        volta = cls(_start=start, _backs=backs, _skips=skips)

        volta.attach(sink=sink)
        return volta

    @classmethod
    def reconstruct(
        cls,
        *,
        id: str,
        start: TemporalAnchor,
        backs: Sequence[JumpRule],
        skips: Sequence[JumpRule],
        sink: MutationSink = DIRECT_SINK,
    ) -> Volta:
        volta = cls(id=id, _start=start, _backs=tuple(backs), _skips=tuple(skips))

        volta.attach(sink=sink)
        return volta
