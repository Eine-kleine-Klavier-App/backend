from collections.abc import Generator, Sequence
from itertools import pairwise

from piano_app.domain.score.document.models import ScoreEntity
from piano_app.domain.score.document.models.material import Note, NoteCarrier, RestCarrier
from piano_app.domain.score.document.models.notation import Articulation, Ornament, RhythmicSize
from piano_app.domain.score.document.models.structural.rhythm import (
    LeafRhythmicContainer,
    RhythmicContainerParent,
)
from piano_app.domain.score.document.services.mutation.engine.analyzers.base import expect_sent
from piano_app.domain.score.document.services.mutation.engine.analyzers.rhythmic.pieces import (
    Piece,
)
from piano_app.domain.score.document.services.mutation.engine.typing import (
    MutationAnalysis,
    MutationWorkItem,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.material import (
    CreateNoteCarrierRequest,
    CreateNoteRequest,
    CreateRestCarrierRequest,
    CreateRestRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.relations import (
    CreateTieRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.rhythmic import (
    CreateLeafRequest,
    NoteContent,
    RestContent,
)

# Helpers for an analyzer to delegate to with ``yield from``: they are not analyzers, so
# unlike an analyzer they hand back what they created.
type _Work[T] = Generator[MutationWorkItem, ScoreEntity | None, T]


def create_note(*, carrier: NoteCarrier, note: NoteContent) -> _Work[Note]:
    """A note on ``carrier``, as ``note`` describes it."""
    return expect_sent(
        sent=(
            yield CreateNoteRequest(
                carrier=carrier,
                staff=note.staff,
                staff_step=note.staff_step,
                accidental=note.accidental,
                fingering=note.fingering,
            )
        ),
        expected=Note,
    )


def create_piece(
    *,
    scope: RhythmicContainerParent,
    piece: Piece,
    content: Sequence[NoteContent] | RestContent,
    articulations: frozenset[Articulation] = frozenset(),
    ornament: Ornament = Ornament.NONE,
) -> _Work[tuple[LeafRhythmicContainer, list[Note]]]:
    """A new leaf for ``piece`` in ``scope`` with its carrier and what ``content`` says: a
    note carrier holding the notes, or a rest carrier holding the rest. The leaf and the notes
    created, in the order given."""
    leaf: LeafRhythmicContainer = expect_sent(
        sent=(
            yield CreateLeafRequest(
                scope=scope,
                measure=piece.measure,
                position=piece.position,
                written_size=RhythmicSize(value=piece.written_value, count=1),
            )
        ),
        expected=LeafRhythmicContainer,
    )

    if isinstance(content, RestContent):
        rest_carrier: RestCarrier = expect_sent(
            sent=(yield CreateRestCarrierRequest(owner=leaf)),
            expected=RestCarrier,
        )
        yield CreateRestRequest(carrier=rest_carrier, staff=content.staff)

        return leaf, []

    note_carrier: NoteCarrier = expect_sent(
        sent=(
            yield CreateNoteCarrierRequest(
                owner=leaf, articulations=articulations, ornament=ornament
            )
        ),
        expected=NoteCarrier,
    )
    notes: list[Note] = []
    for note_content in content:
        notes.append((yield from create_note(carrier=note_carrier, note=note_content)))

    return leaf, notes


def tie_pieces(*, notes_by_piece: Sequence[Sequence[Note]]) -> MutationAnalysis:
    """Each note of a piece tied to its counterpart in the next piece, after all exist."""
    for start_notes, end_notes in pairwise(notes_by_piece):
        for start_note, end_note in zip(start_notes, end_notes, strict=True):
            yield CreateTieRequest(start_note=start_note, end_note=end_note)
