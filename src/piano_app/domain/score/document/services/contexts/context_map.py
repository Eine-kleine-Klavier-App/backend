from collections.abc import Iterator, Sequence
from fractions import Fraction

from piano_app.domain.score.document.models.context import (
    Context,
    SpanContext,
    StaffScoped,
    VoicesScoped,
)
from piano_app.domain.score.document.models.structural import Voice
from piano_app.domain.score.document.services.geometry import Point, Span
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry


class ContextMap:
    """Reads which region of the timeline each context of the score governs.

    A span context governs from its start to its end. A point context governs from its
    position until the next context of the same concrete type and the same scope starts —
    the same staff for a staff-scoped one, the whole score otherwise — or until the end of
    the score. A voices-scoped point context is read voice by voice: for each of its voices it
    governs until the next context of its type that names that voice starts, so one context
    may govern one voice longer than another.

    Read through the geometry it is given and holding nothing of its own, so it answers
    for the score as that geometry does; every region is a snapshot on the global timeline.
    """

    def __init__(self, *, geometry: ScoreGeometry) -> None:
        self._geometry: ScoreGeometry = geometry

    def region_of(self, *, context: Context) -> Span:
        """The region ``context`` governs, on the global timeline. For a voices-scoped point
        context, up to where it stops governing the last of its voices."""
        start: Point = self._geometry.point_of(anchor=context.start)

        if isinstance(context, SpanContext):
            return Span.between(start=start, end=self._geometry.end_of(context=context))

        if isinstance(context, VoicesScoped):
            ends: list[Point] = [
                self._end_of_governing(context=context, voice=voice) for voice in context.voices
            ]
            return Span.between(start=start, end=max(ends, key=lambda end: end.value))

        return Span.between(start=start, end=self._end_of_governing(context=context, voice=None))

    def governed_voices(self, *, context: VoicesScoped, at: Point) -> list[Voice]:
        """The voices of a voices-scoped point context that it still governs at ``at``: those
        whose next context of the same type starts after ``at``, or does not exist."""
        return [
            voice
            for voice in context.voices
            if self._end_of_governing(context=context, voice=voice).value
            > at.to(frame=self._geometry.root).value
        ]

    def _end_of_governing(self, *, context: Context, voice: Voice | None) -> Point:
        """Where a point context stops governing: the start of the next context of its type
        in the same scope — for ``voice``, if given — or the end of the score."""
        for measure, _ in self._geometry.measure_regions():
            for anchor in measure.anchors:
                if not context.start.precedes(anchor):
                    continue

                for other in anchor.starting_contexts:
                    if type(other) is not type(context):
                        continue

                    same_scope: bool = True
                    if isinstance(context, StaffScoped) and isinstance(other, StaffScoped):
                        same_scope = other.staff is context.staff
                    elif (
                        voice is not None
                        and isinstance(context, VoicesScoped)
                        and isinstance(other, VoicesScoped)
                    ):
                        same_scope = voice in other.voices

                    if same_scope:
                        return self._geometry.point_of(anchor=anchor)

        # the timeline ends where the last measure does
        return Point(frame=self._geometry.root, value=self._geometry.root.extent)

    def spans_across(
        self,
        *,
        span_type: type[SpanContext],
        start: Fraction,
        end: Fraction,
        voices: Sequence[Voice] | None,
    ) -> list[SpanContext]:
        """The spans of ``span_type`` that start before ``start`` and end after ``end``, so
        that all of that stretch lies strictly inside them; only those naming one of
        ``voices``, if given. Positions are on the global timeline."""
        return [
            context
            for context in self.contexts()
            if isinstance(context, span_type)
            and self._names_a_voice(context=context, voices=voices)
            and self._geometry.point_of(anchor=context.start).value < start
            and self._geometry.end_of(context=context).value > end
        ]

    def spans_overlapping(
        self,
        *,
        span_type: type[SpanContext],
        start: Fraction,
        end: Fraction,
        voices: Sequence[Voice] | None,
        ignore: Context | None = None,
    ) -> list[SpanContext]:
        """The spans of ``span_type`` that share a stretch with the half-open ``[start, end)``,
        other than ``ignore``; only those naming one of ``voices``, if given."""
        return [
            context
            for context in self.contexts()
            if isinstance(context, span_type)
            and context is not ignore
            and self._names_a_voice(context=context, voices=voices)
            and self._geometry.point_of(anchor=context.start).value < end
            and start < self._geometry.end_of(context=context).value
        ]

    def points_inside(
        self,
        *,
        point_type: type[Context],
        start: Fraction,
        end: Fraction,
        voices: Sequence[Voice] | None,
        ignore: Context | None = None,
    ) -> list[Context]:
        """The contexts of ``point_type`` strictly between ``start`` and ``end``, other than
        ``ignore``; only those naming one of ``voices``, if given."""
        return [
            context
            for context in self.contexts()
            if isinstance(context, point_type)
            and context is not ignore
            and self._names_a_voice(context=context, voices=voices)
            and start < self._geometry.point_of(anchor=context.start).value < end
        ]

    def contexts(self) -> Iterator[Context]:
        """Every context of the score, in measure order."""
        for measure, _ in self._geometry.measure_regions():
            for anchor in measure.anchors:
                yield from anchor.starting_contexts

    @staticmethod
    def _names_a_voice(*, context: Context, voices: Sequence[Voice] | None) -> bool:
        if voices is None:
            return True

        return isinstance(context, VoicesScoped) and any(
            voice in context.voices for voice in voices
        )
