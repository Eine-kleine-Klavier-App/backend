from bisect import bisect_left, bisect_right
from collections.abc import Iterator
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import Context, SpanContext, VoicesScoped
from piano_app.domain.score.document.models.structural import TemporalAnchor, Voice
from piano_app.domain.score.document.services.geometry import Piece, Span
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.indexing import Index

from .scope import Scope, scopes_of


@dataclass(frozen=True, slots=True, kw_only=True)
class _Entry:
    """A context of one kind in one scope, with where it starts and, for a span, ends on the
    global timeline."""

    start: Fraction
    end: Fraction | None
    context: Context


class ContextIndex(Index):
    """Which contexts hold where: every kind, keyed by its scope, answered as pieces.

    A point context governs from its position until the next of its kind in the same scope;
    a span context from its start to its end. The entries of a kind are built when first read
    and kept until a context of that kind, an anchor it sits on or a measure changes. Read
    through the geometry it is given, on the global timeline.
    """

    def __init__(self, *, document: ScoreDocument, geometry: ScoreGeometry) -> None:
        self._document: ScoreDocument = document
        self._geometry: ScoreGeometry = geometry
        self._by_kind: dict[type[Context], dict[Scope, list[_Entry]]] = {}

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
        start to its end; a point context from its position until the next of its kind in each
        scope it governs — for a context on several voices, up to where it stops governing the
        last of them."""
        start: Fraction = self._geometry.point_of(anchor=context.start).value
        end: Fraction
        if isinstance(context, SpanContext):
            end = self._geometry.end_of(context=context).value
        else:
            end = max(
                self.piece_at(kind=type(context), point=start, scope=scope).span.end
                for scope in scopes_of(context=context)
            )

        return Span(frame=self._geometry.root, start=start, length=end - start)

    def governed_voices(self, *, context: VoicesScoped, at: Fraction) -> list[Voice]:
        """The voices of a context on voices that it still governs at ``at``: those whose next
        context of its kind starts after ``at``, or does not exist."""
        start: Fraction = self._geometry.point_of(anchor=context.start).value

        return [
            voice
            for voice in context.voices
            if self.piece_at(
                kind=type(context), point=start, scope=Scope.of_voice(voice=voice)
            ).span.end
            > at
        ]

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

    def invalidate_anchor(self, *, anchor: TemporalAnchor) -> None:
        for context in (*anchor.starting_contexts, *anchor.ending_contexts):
            self._by_kind.pop(type(context), None)

    def invalidate_context(self, *, context: Context) -> None:
        self._by_kind.pop(type(context), None)

    def _entries(self, *, kind: type[Context], scope: Scope) -> list[_Entry]:
        """The entries of a kind in a scope, by where they start."""
        by_scope: dict[Scope, list[_Entry]] | None = self._by_kind.get(kind)
        if by_scope is None:
            by_scope = {}
            for measure in self._document.measures:
                for anchor in measure.anchors:
                    for context in anchor.starting_contexts:
                        if type(context) is not kind:
                            continue

                        entry: _Entry = _Entry(
                            start=self._geometry.point_of(anchor=context.start).value,
                            end=(
                                self._geometry.end_of(context=context).value
                                if isinstance(context, SpanContext)
                                else None
                            ),
                            context=context,
                        )
                        for governed in scopes_of(context=context):
                            by_scope.setdefault(governed, []).append(entry)

            for entries in by_scope.values():
                entries.sort(key=lambda each: each.start)

            self._by_kind[kind] = by_scope

        return by_scope.get(scope, [])

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
