from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction

import pytest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import ClefChange, Context, OctaveTransposition
from piano_app.domain.score.document.models.notation import (
    Clef,
    RhythmicSize,
    RhythmicValue,
)
from piano_app.domain.score.document.models.structural import (
    Measure,
    MeasurePosition,
    Staff,
    Voice,
)
from piano_app.domain.score.document.services.contexts import ContextIndex
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation import MutationEngine
from piano_app.domain.score.document.services.mutation.engine.factory import build_engine
from piano_app.domain.score.document.services.mutation.instructions import MutationRequest
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateClefChangeRequest,
    CreateKeySignatureChangeRequest,
    CreateOctaveTranspositionRequest,
    UpdateContextEndRequest,
    UpdateContextStartRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.intent import (
    InsertMeasureRequest,
    RemoveRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.structural import (
    CreateEmptyMeasureRequest,
    DeleteEmptyMeasureRequest,
    UpdateMeasureTimeSignatureRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.temporal import (
    UpdateTemporalAnchorRequest,
)
from piano_app.domain.score.document.services.pitch.score_pitch import ScorePitch

from ...scene import check_pitch_at_checkpoint, size

# The transaction's pitch index must answer like one built from scratch after every operation
# that can change a pitch rule. The index layer marks the index from the journal, so a missing
# rule shows up here: a first pass warms the index at its check points, the operation then runs
# in the same transaction and its check points compare the index with a fresh one.

_Q: Fraction = Fraction(1, 4)
_EIGHTH: Fraction = Fraction(1, 8)


@dataclass(frozen=True, slots=True, kw_only=True)
class _Scene:
    document: ScoreDocument
    measures: list[Measure]
    staff: Staff
    other: Staff
    bass: ClefChange
    octave: OctaveTransposition


def _position(*, at: Fraction) -> MeasurePosition:
    return MeasurePosition.of_fraction(fraction=at)


def _scene() -> _Scene:
    """Four 4/4 measures, two staffs. The first staff has a treble clef at the start, a bass
    clef at the start of measure two and an octave line inside measure one; the other has a
    treble clef only. The last measure is empty."""
    four_four: RhythmicSize = size(RhythmicValue.QUARTER, 4)
    measures: list[Measure] = [Measure.create(time_signature=four_four) for _ in range(4)]
    staff, other = Staff(), Staff()
    document: ScoreDocument = ScoreDocument.create(
        voices=[Voice()], staffs=[staff, other], measures=measures
    )
    setup: list[MutationRequest] = [
        CreateClefChangeRequest(
            measure=measures[0], position=_position(at=Fraction(0)), staff=staff, clef=Clef.TREBLE
        ),
        CreateClefChangeRequest(
            measure=measures[0], position=_position(at=Fraction(0)), staff=other, clef=Clef.TREBLE
        ),
        CreateClefChangeRequest(
            measure=measures[2], position=_position(at=Fraction(0)), staff=staff, clef=Clef.BASS
        ),
        CreateOctaveTranspositionRequest(
            start_measure=measures[1],
            start_position=_position(at=_Q),
            end_measure=measures[1],
            end_position=_position(at=Fraction(1, 2)),
            staff=staff,
            octaves=1,
        ),
    ]
    build_engine().process(document=document, requests=setup)

    bass: Context = next(
        context
        for context in staff.contexts
        if isinstance(context, ClefChange) and context.clef is Clef.BASS
    )
    octave: Context = next(
        context for context in staff.contexts if isinstance(context, OctaveTransposition)
    )
    assert isinstance(bass, ClefChange) and isinstance(octave, OctaveTransposition)

    return _Scene(
        document=document,
        measures=measures,
        staff=staff,
        other=other,
        bass=bass,
        octave=octave,
    )


def _operations() -> dict[str, Callable[[_Scene], MutationRequest]]:
    three_four: RhythmicSize = size(RhythmicValue.QUARTER, 3)
    four_four: RhythmicSize = size(RhythmicValue.QUARTER, 4)
    return {
        "append a measure": lambda s: CreateEmptyMeasureRequest(
            document=s.document, before=None, time_signature=four_four
        ),
        "insert a measure": lambda s: InsertMeasureRequest(
            document=s.document, before=s.measures[1]
        ),
        "create an empty measure": lambda s: CreateEmptyMeasureRequest(
            document=s.document, before=s.measures[1], time_signature=three_four
        ),
        "delete a measure": lambda s: RemoveRequest(document=s.document, targets=(s.measures[3],)),
        "delete an empty measure": lambda s: DeleteEmptyMeasureRequest(
            document=s.document, target=s.measures[3]
        ),
        "change a time signature": lambda s: UpdateMeasureTimeSignatureRequest(
            target=s.measures[1], time_signature=three_four
        ),
        "move an anchor carrying a clef": lambda s: UpdateTemporalAnchorRequest(
            target=s.bass.start, measure=s.measures[2], position=_position(at=_Q)
        ),
        "create a clef": lambda s: CreateClefChangeRequest(
            measure=s.measures[3],
            position=_position(at=Fraction(0)),
            staff=s.staff,
            clef=Clef.TREBLE,
        ),
        "replace the initial clef": lambda s: CreateClefChangeRequest(
            measure=s.measures[0], position=_position(at=Fraction(0)), staff=s.other, clef=Clef.BASS
        ),
        "create an octave line": lambda s: CreateOctaveTranspositionRequest(
            start_measure=s.measures[3],
            start_position=_position(at=_Q),
            end_measure=s.measures[3],
            end_position=_position(at=Fraction(1, 2)),
            staff=s.other,
            octaves=-1,
        ),
        "delete a clef": lambda s: DeleteRequest(target=s.bass),
        "delete an octave line": lambda s: DeleteRequest(target=s.octave),
        "move a clef": lambda s: UpdateContextStartRequest(
            target=s.bass, measure=s.measures[2], position=_position(at=Fraction(1, 2))
        ),
        "move an octave line start": lambda s: UpdateContextStartRequest(
            target=s.octave, measure=s.measures[1], position=_position(at=_EIGHTH)
        ),
        "move an octave line end": lambda s: UpdateContextEndRequest(
            target=s.octave, measure=s.measures[1], position=_position(at=Fraction(3, 4))
        ),
    }


@pytest.mark.unit
@pytest.mark.parametrize("name", list(_operations()))
def test_the_transactions_pitch_matches_a_fresh_index_after_an_operation(name: str) -> None:
    scene: _Scene = _scene()
    checks: list[None] = []

    def check(pitch: ScorePitch, geometry: ScoreGeometry, document: ScoreDocument) -> None:
        check_pitch_at_checkpoint(pitch=pitch, geometry=geometry, document=document)
        checks.append(None)

    engine: MutationEngine = build_engine(checkpoint_pitch_check=check)
    warm: MutationRequest = CreateKeySignatureChangeRequest(
        measure=scene.measures[0], position=_position(at=Fraction(0)), staff=scene.staff
    )
    operation: MutationRequest = _operations()[name](scene)

    with engine.transaction(document=scene.document) as transaction:
        transaction.run(requests=[warm])
        warmed: int = len(checks)
        transaction.run(requests=[operation])

    assert warmed > 0
    assert len(checks) > warmed


@pytest.mark.unit
def test_the_check_notices_a_stale_index() -> None:
    """The comparison itself: an index warmed before a context moves, left alone, differs."""
    scene: _Scene = _scene()
    geometry: ScoreGeometry = ScoreGeometry(document=scene.document)
    pitch: ScorePitch = ScorePitch(
        document=scene.document,
        geometry=geometry,
        contexts=ContextIndex(document=scene.document, geometry=geometry),
    )
    check_pitch_at_checkpoint(pitch=pitch, geometry=geometry, document=scene.document)

    build_engine().process(
        document=scene.document,
        requests=[DeleteRequest(target=scene.bass)],
    )
    geometry.invalidate_measures()

    with pytest.raises(AssertionError):
        check_pitch_at_checkpoint(pitch=pitch, geometry=geometry, document=scene.document)
