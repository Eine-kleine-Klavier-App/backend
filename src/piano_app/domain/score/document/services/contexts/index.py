from bisect import bisect_left, bisect_right
from collections.abc import Iterator
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import Context, SpanContext
from piano_app.domain.score.document.models.structural import TemporalAnchor
from piano_app.domain.score.document.services.geometry import Piece, Span
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.indexing import Index

from .scope import Scope, scope_of


@dataclass(frozen=True, slots=True, kw_only=True)
class _Entry:
    """A context of one kind in one scope, with where it starts and, for a span, ends on the
    global timeline."""

    start: Fraction
    end: Fraction | None
    context: Context


@dataclass(frozen=True, slots=True, kw_only=True)
class _Placed:
    """Where a context's entry was put: the entry and the scope whose list holds it."""

    entry: _Entry
    scope: Scope


class ContextIndex(Index):
    """Which contexts hold where: every kind, keyed by its scope, answered as pieces.

    A point context governs from its position until the next of its kind in the same scope;
    a span context from its start to its end. The entries of a kind are built whole when first
    read. After that a change marks only the contexts it touched, and the next read takes each
    out of the scope it was in and, if it is still held, puts it into the scope it governs
    now, by where it starts. Read through the geometry it is given, on the global timeline.
    """

    def __init__(self, *, document: ScoreDocument, geometry: ScoreGeometry) -> None:
        self._document: ScoreDocument = document
        self._geometry: ScoreGeometry = geometry
        self._by_kind: dict[type[Context], dict[Scope, list[_Entry]]] = {}
        self._placed: dict[type[Context], dict[Context, _Placed]] = {}
        self._dirty: dict[type[Context], set[Context]] = {}

    def piece_at[T: Context](
        self,
        *,
        kind: type[T],
        point: Fraction,
        scope: Scope,
    ) -> Piece[T | None, T]:
        """The piece of ``kind`` in ``scope`` that holds ``point``, from the boundary of its
        kind before it to the boundary after it."""
        extent: Fraction = self._geometry.root.extent
        if not 0 <= point < extent:
            raise ValueError("A point is asked for outside the timeline.")

        entries: list[_Entry] = self._entries(kind=kind, scope=scope)
        bounds: list[Fraction] = self._boundaries(entries=entries)
        start: Fraction = max((bound for bound in bounds if bound <= point), default=Fraction(0))
        end: Fraction = min((bound for bound in bounds if bound > point), default=extent)

        return self._piece(kind=kind, entries=entries, start=start, end=end)

    def pieces_over[T: Context](
        self,
        *,
        kind: type[T],
        start: Fraction,
        end: Fraction,
        scope: Scope,
    ) -> list[Piece[T | None, T]]:
        """The pieces of ``kind`` in ``scope`` that tile ``[start, end)`` exactly, cut at the
        start and the end of every context of the kind inside it."""
        if not 0 <= start < end <= self._geometry.root.extent:
            raise ValueError("An interval is asked for outside the timeline.")

        entries: list[_Entry] = self._entries(kind=kind, scope=scope)
        cuts: list[Fraction] = sorted(
            {start, end}
            | {bound for bound in self._boundaries(entries=entries) if start < bound < end}
        )

        return [
            self._piece(kind=kind, entries=entries, start=low, end=high)
            for low, high in pairwise(cuts)
        ]

    def starting_at[T: Context](
        self,
        *,
        kind: type[T],
        point: Fraction,
        scope: Scope,
    ) -> list[T]:
        """The contexts of ``kind`` in ``scope`` that start exactly at ``point``."""
        entries: list[_Entry] = self._entries(kind=kind, scope=scope)
        starts: list[Fraction] = [entry.start for entry in entries]
        found: list[T] = []
        for entry in entries[bisect_left(starts, point) : bisect_right(starts, point)]:
            if isinstance(entry.context, kind):
                found.append(entry.context)

        return found

    def region_of(self, *, context: Context) -> Span:
        """The region ``context`` governs, on the global timeline: a span context from its
        start to its end; a point context from its position until the next of its kind in its
        scope."""
        start: Fraction = self._geometry.point_of(anchor=context.start).value
        end: Fraction
        if isinstance(context, SpanContext):
            end = self._geometry.end_of(context=context).value
        else:
            end = self.piece_at(
                kind=type(context), point=start, scope=scope_of(context=context)
            ).span.end

        return Span(frame=self._geometry.root, start=start, length=end - start)

    def contexts_of[T: Context](self, *, kind: type[T], scope: Scope) -> list[T]:
        """The contexts of ``kind`` in ``scope``, by where they start."""
        found: list[T] = []
        for entry in self._entries(kind=kind, scope=scope):
            if isinstance(entry.context, kind):
                found.append(entry.context)

        return found

    def contexts(self) -> Iterator[Context]:
        """Every context of the score, in measure order."""
        for measure in self._document.measures:
            for anchor in measure.anchors:
                yield from anchor.starting_contexts

    def invalidate_measures(self) -> None:
        self._by_kind.clear()
        self._placed.clear()
        self._dirty.clear()

    def invalidate_anchor(self, *, anchor: TemporalAnchor) -> None:
        # an anchor moving shifts the start of what begins on it and the end of what ends on it
        for context in (*anchor.starting_contexts, *anchor.ending_contexts):
            self.invalidate_context(context=context)

    def invalidate_context(self, *, context: Context) -> None:
        # a kind nobody has read has no entries to keep right
        kind: type[Context] = type(context)
        if kind in self._by_kind:
            self._dirty.setdefault(kind, set()).add(context)

    def _entries(self, *, kind: type[Context], scope: Scope) -> list[_Entry]:
        """The entries of a kind in a scope, by where they start."""
        by_scope: dict[Scope, list[_Entry]] | None = self._by_kind.get(kind)
        if by_scope is None:
            by_scope = self._build(kind=kind)
        elif kind in self._dirty:
            self._heal(kind=kind, by_scope=by_scope)

        return by_scope.get(scope, [])

    def _build(self, *, kind: type[Context]) -> dict[Scope, list[_Entry]]:
        by_scope: dict[Scope, list[_Entry]] = {}
        placed: dict[Context, _Placed] = {}
        for measure in self._document.measures:
            for anchor in measure.anchors:
                for context in anchor.starting_contexts:
                    if type(context) is not kind:
                        continue

                    placed[context] = _Placed(
                        entry=self._entry_of(context=context),
                        scope=scope_of(context=context),
                    )
                    by_scope.setdefault(placed[context].scope, []).append(placed[context].entry)

        for entries in by_scope.values():
            entries.sort(key=lambda each: each.start)

        self._by_kind[kind] = by_scope
        self._placed[kind] = placed

        return by_scope

    def _heal(self, *, kind: type[Context], by_scope: dict[Scope, list[_Entry]]) -> None:
        placed: dict[Context, _Placed] = self._placed[kind]
        dirty: set[Context] = self._dirty.pop(kind)

        # a read that cannot answer leaves the entries half healed, so they go and are built
        # again by the next read
        try:
            for context in dirty:
                taken: _Placed | None = placed.pop(context, None)
                if taken is not None:
                    by_scope[taken.scope].remove(taken.entry)

            for context in dirty:
                if not self._is_held(context=context):
                    continue

                placed[context] = _Placed(
                    entry=self._entry_of(context=context),
                    scope=scope_of(context=context),
                )
                entries: list[_Entry] = by_scope.setdefault(placed[context].scope, [])
                entries.insert(
                    bisect_right(
                        entries, self._order_of(entry=placed[context].entry), key=self._order_of
                    ),
                    placed[context].entry,
                )
        except Exception:
            self._by_kind.pop(kind, None)
            self._placed.pop(kind, None)
            raise

    def _entry_of(self, *, context: Context) -> _Entry:
        return _Entry(
            start=self._geometry.point_of(anchor=context.start).value,
            end=(
                self._geometry.end_of(context=context).value
                if isinstance(context, SpanContext)
                else None
            ),
            context=context,
        )

    @staticmethod
    def _order_of(entry: _Entry) -> tuple[Fraction, int]:
        """Where an entry stands among the others: by its start, and at one start in the order
        its anchor holds its contexts — the order a build lists them in."""
        return entry.start, entry.context.start.starting_contexts.index(entry.context)

    @staticmethod
    def _is_held(*, context: Context) -> bool:
        """Whether the score still lists the context: on an anchor of a measure."""
        anchor: TemporalAnchor = context.start

        return context in anchor.starting_contexts and anchor in anchor.measure.anchors

    @staticmethod
    def _boundaries(*, entries: list[_Entry]) -> list[Fraction]:
        """Where a piece of the kind can end: every start and, for a span kind, every end."""
        bounds: list[Fraction] = []
        for entry in entries:
            bounds.append(entry.start)
            if entry.end is not None:
                bounds.append(entry.end)

        return bounds

    def _piece[T: Context](
        self,
        *,
        kind: type[T],
        entries: list[_Entry],
        start: Fraction,
        end: Fraction,
    ) -> Piece[T | None, T]:
        """The piece over ``[start, end)``, which lies between two boundaries of the kind."""
        sources: list[T] = []
        if issubclass(kind, SpanContext):
            for entry in entries:
                if (
                    isinstance(entry.context, kind)
                    and entry.end is not None
                    and entry.start <= start
                    and entry.end >= end
                ):
                    sources.append(entry.context)
        else:
            governing: T | None = None
            for entry in entries:
                if isinstance(entry.context, kind) and entry.start <= start:
                    governing = entry.context

            if governing is not None:
                sources.append(governing)

        return Piece(
            span=Span(frame=self._geometry.root, start=start, length=end - start),
            value=sources[-1] if sources else None,
            sources=tuple(sources),
        )
