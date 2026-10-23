from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction

from piano_app.domain.score.document.models.context.point.volta import check_fragment_passes


@dataclass(frozen=True, slots=True, kw_only=True)
class Boundary[R]:
    """A place of the timeline a part of a volta begins or ends at, with whatever stands for
    it in the score (``ref``: the planner never looks at it, it only carries it)."""

    position: Fraction
    ref: R


@dataclass(frozen=True, slots=True, kw_only=True)
class Fragment[R]:
    """A fragment of a volta: where it ends and the passes it is played in. It starts where
    the one before it ends."""

    end: Boundary[R]
    passes: frozenset[int]


@dataclass(frozen=True, slots=True, kw_only=True)
class Layout[R]:
    """A volta laid out on the timeline: where its body starts and ends and its fragments in
    order. The plans below take a layout and give the one a change leads to, without touching
    the score, so every rule of changing a volta can be read and tested apart from it."""

    start: Boundary[R]
    body_end: Boundary[R]
    fragments: tuple[Fragment[R], ...]

    @property
    def stored_passes(self) -> int:
        """How many passes the stored fragments hold: every pass before the last one."""
        return sum(len(fragment.passes) for fragment in self.fragments)


def _renumbered(*, passes: frozenset[int], removed: frozenset[int]) -> frozenset[int]:
    """The passes after the removed ones are gone: each shifts down by how many removed
    passes lay before it."""
    return frozenset(number - sum(1 for gone in removed if gone < number) for number in passes)


def _without[R](
    *,
    start: Boundary[R],
    body_end: Boundary[R],
    fragments: Sequence[Fragment[R]],
    absorbed: Sequence[Fragment[R]],
) -> Layout[R] | None:
    """The layout with the fragments of ``absorbed`` gone and their passes taken out of the
    numbering; none when no fragment is left."""
    if not fragments:
        return None

    removed: frozenset[int] = frozenset().union(*(fragment.passes for fragment in absorbed))

    return Layout(
        start=start,
        body_end=body_end,
        fragments=tuple(
            Fragment(end=fragment.end, passes=_renumbered(passes=fragment.passes, removed=removed))
            for fragment in fragments
        ),
    )


def move_boundary[R](
    *,
    layout: Layout[R],
    index: int,
    to: Boundary[R],
) -> Layout[R] | None:
    """The layout after a boundary is dragged to ``to``; none when the volta is left with no
    fragment.

    Boundary 0 is where the body ends, boundary ``i`` where fragment ``i`` ends. The body
    never goes: it keeps something after its start. A boundary between two parts takes the
    place from the part on one side and gives it to the part on the other; a fragment
    covered whole by the one that grows is absorbed, with its passes, and the later passes
    shift down. The end of the last fragment moves alone, over nothing but its own length.
    """
    count: int = len(layout.fragments)
    if not 0 <= index <= count:
        raise ValueError("A volta has no such boundary.")

    ends: list[Boundary[R]] = [layout.body_end, *(fragment.end for fragment in layout.fragments)]
    if to.position <= layout.start.position:
        raise ValueError("The body of a volta must end after it starts.")

    if to.position == ends[index].position:
        return layout

    if index == count:
        if to.position <= ends[count - 1].position:
            raise ValueError("A fragment of a volta must end after it starts.")

        return Layout(
            start=layout.start,
            body_end=layout.body_end,
            fragments=(
                *layout.fragments[:-1],
                Fragment(end=to, passes=layout.fragments[-1].passes),
            ),
        )

    fragments: list[Fragment[R]] = list(layout.fragments)
    body_end: Boundary[R] = layout.body_end
    absorbed: list[Fragment[R]]
    if to.position > ends[index].position:
        # the part before the boundary grows over the fragments it covers whole
        covered: list[int] = [
            number for number in range(index + 1, count + 1) if ends[number].position <= to.position
        ]
        absorbed = [fragments[number - 1] for number in covered]
        fragments = [
            fragments[number - 1] for number in range(1, count + 1) if number not in covered
        ]
        if index == 0:
            if not fragments:
                return None

            body_end = to
        else:
            fragments[index - 1] = Fragment(end=to, passes=fragments[index - 1].passes)
    else:
        # the fragment after the boundary grows over the fragments before it, whole or in part
        covered = [
            number for number in range(1, index + 1) if ends[number - 1].position >= to.position
        ]
        absorbed = [fragments[number - 1] for number in covered]
        kept_before: int = index - len(covered)
        fragments = [
            fragments[number - 1] for number in range(1, count + 1) if number not in covered
        ]
        if kept_before == 0:
            body_end = to
        else:
            fragments[kept_before - 1] = Fragment(end=to, passes=fragments[kept_before - 1].passes)

    return _without(start=layout.start, body_end=body_end, fragments=fragments, absorbed=absorbed)


def move_start[R](*, layout: Layout[R], to: Boundary[R]) -> Layout[R]:
    """The layout after the start of the body is dragged to ``to``: only the body changes."""
    if to.position >= layout.body_end.position:
        raise ValueError("The body of a volta must end after it starts.")

    return Layout(start=to, body_end=layout.body_end, fragments=layout.fragments)


def set_passes[R](*, layout: Layout[R], index: int, passes: frozenset[int]) -> Layout[R]:
    """The layout after the passes of fragment ``index`` (counted from zero, so not the first
    one) are set.

    The first fragment is played in whatever the others leave, so it is not set. A pass named
    beyond those the fragments hold makes the volta longer by passes. A pass named here is
    taken from the fragment that had it: one that is left with no pass is refused."""
    if not 1 <= index < len(layout.fragments):
        raise ValueError("The first fragment is played in the passes the others leave.")

    if not passes:
        raise ValueError("A fragment of a volta is played in at least one pass.")

    later: list[frozenset[int]] = [fragment.passes - passes for fragment in layout.fragments[1:]]
    later[index - 1] = passes
    last: int = max(layout.stored_passes, max(passes))
    first: frozenset[int] = frozenset(range(1, last + 1)) - frozenset().union(*later)
    check_fragment_passes(passes=[first, *later])

    return Layout(
        start=layout.start,
        body_end=layout.body_end,
        fragments=tuple(
            Fragment(end=fragment.end, passes=new_passes)
            for fragment, new_passes in zip(layout.fragments, [first, *later], strict=True)
        ),
    )


def set_times[R](*, layout: Layout[R], times: int) -> Layout[R]:
    """The layout of a volta played ``times`` times: the first fragment is played in every pass
    before the last that the others do not hold. A later fragment keeps its passes, so ``times``
    may not leave one of them beyond the last pass."""
    if times < 2:
        raise ValueError("A volta is played at least twice.")

    last: int = times - 1
    later: list[frozenset[int]] = [fragment.passes for fragment in layout.fragments[1:]]
    if any(max(passes) > last for passes in later):
        raise ValueError("An ending is played in a pass that the volta would no longer have.")

    first: frozenset[int] = frozenset(range(1, last + 1)) - frozenset().union(*later)
    check_fragment_passes(passes=[first, *later])

    return Layout(
        start=layout.start,
        body_end=layout.body_end,
        fragments=tuple(
            Fragment(end=fragment.end, passes=new_passes)
            for fragment, new_passes in zip(layout.fragments, [first, *later], strict=True)
        ),
    )


def append_fragment[R](*, layout: Layout[R], end: Boundary[R]) -> Layout[R]:
    """The layout with a fragment added after the last one, ending at ``end``. It is played in
    the pass that was the last one, and the pass after it becomes the last."""
    if end.position <= layout.fragments[-1].end.position:
        raise ValueError("A fragment of a volta must end after it starts.")

    return Layout(
        start=layout.start,
        body_end=layout.body_end,
        fragments=(
            *layout.fragments,
            Fragment(end=end, passes=frozenset({layout.stored_passes + 1})),
        ),
    )


def split_last_fragment[R](*, layout: Layout[R], at: Boundary[R]) -> Layout[R]:
    """The layout with the last fragment cut at ``at``: the first part keeps its passes and
    the second, up to the old end, is played in the pass that was the last one."""
    before: Fraction = (
        layout.fragments[-2].end.position if len(layout.fragments) > 1 else layout.body_end.position
    )
    last: Fragment[R] = layout.fragments[-1]
    if not before < at.position < last.end.position:
        raise ValueError("A fragment is cut inside the last fragment of a volta.")

    return Layout(
        start=layout.start,
        body_end=layout.body_end,
        fragments=(
            *layout.fragments[:-1],
            Fragment(end=at, passes=last.passes),
            Fragment(end=last.end, passes=frozenset({layout.stored_passes + 1})),
        ),
    )


def collapse[R](
    *,
    layout: Layout[R],
    inside: Callable[[R], bool],
    to: Boundary[R],
) -> Layout[R] | None:
    """The layout once every boundary standing for a place that ``inside`` picks out is
    drawn together to ``to``: what a measure's removal does to the boundaries lying in it.

    A fragment left with no length is absorbed, with its passes, and the later passes shift
    down; none when the body is left with no length or no fragment is left."""
    start: Boundary[R] = to if inside(layout.start.ref) else layout.start
    body_end: Boundary[R] = to if inside(layout.body_end.ref) else layout.body_end
    if body_end.position <= start.position:
        return None

    kept: list[Fragment[R]] = []
    absorbed: list[Fragment[R]] = []
    previous: Fraction = body_end.position
    for fragment in layout.fragments:
        end: Boundary[R] = to if inside(fragment.end.ref) else fragment.end
        if end.position <= previous:
            absorbed.append(fragment)
            continue

        kept.append(Fragment(end=end, passes=fragment.passes))
        previous = end.position

    return _without(start=start, body_end=body_end, fragments=kept, absorbed=absorbed)
