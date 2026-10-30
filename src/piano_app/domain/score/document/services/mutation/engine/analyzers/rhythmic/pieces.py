from dataclasses import dataclass
from fractions import Fraction

from piano_app.domain.score.document.models.notation import DottedRhythmicValue
from piano_app.domain.score.document.models.structural import Measure, MeasurePosition
from piano_app.domain.score.document.services.geometry import Point, Span
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.helpers import RhythmicSizeMapper
from piano_app.domain.score.document.services.mutation.instructions import (
    MutationRejectedError,
)

_SIZE_MAPPER: RhythmicSizeMapper = RhythmicSizeMapper()


@dataclass(frozen=True, slots=True, kw_only=True)
class Piece:
    """One notatable piece of a span, in model terms only: where it starts, its written
    value, and its span in the units of the span it was cut from."""

    measure: Measure
    position: MeasurePosition
    written_value: DottedRhythmicValue
    span: Span


def cut_into_pieces(*, geometry: ScoreGeometry, span: Span) -> list[Piece]:
    """The pieces of ``span``: cut at the barlines, each cut spelled in the units of the
    span's own scope. A cut that cannot be spelled is refused."""
    pieces: list[Piece] = []
    for cut in geometry.slice_by_measures(span=span):
        # cut on the timeline, but written in the scope's own units
        written: Span = cut.part.to(frame=span.frame)

        try:
            mapped_sizes: list[DottedRhythmicValue] = _SIZE_MAPPER.spell_duration(
                duration=written.length
            )
        except ValueError as error:
            raise MutationRejectedError(f"Cannot spell a part of {written.length}.") from error

        offset: Fraction = Fraction(0)
        for mapped in mapped_sizes:
            piece_span: Span = Span(
                frame=span.frame,
                start=written.start + offset,
                length=mapped.fraction,
            )
            at: Point = piece_span.start_point.to(frame=geometry.of_measure(measure=cut.region))
            pieces.append(
                Piece(
                    measure=cut.region,
                    position=MeasurePosition.of_fraction(fraction=at.value),
                    written_value=mapped,
                    span=piece_span,
                )
            )

            offset += mapped.fraction

    return pieces


def point_of_piece(*, geometry: ScoreGeometry, piece: Piece) -> Point:
    """Where a piece starts, on the global timeline."""
    return Point(
        frame=geometry.of_measure(measure=piece.measure),
        value=piece.position.value,
    ).to(frame=geometry.root)
