from fractions import Fraction

import pytest

from piano_app.domain.score.document.models.context import ClefChange, Context
from piano_app.domain.score.document.models.notation import Clef, RhythmicValue
from piano_app.domain.score.document.models.structural import (
    MeasurePosition,
    TemporalAnchor,
)
from piano_app.domain.score.document.models.structural.rhythm import LeafRhythmicContainer
from piano_app.domain.score.document.services.geometry.score_geometry import ScoreGeometry
from piano_app.domain.score.document.services.mutation.engine.postprocessors import (
    OrphanAnchorsPostprocessor,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.context import (
    CreateClefChangeRequest,
)
from piano_app.domain.score.document.services.mutation.instructions.requests.delete import (
    DeleteRequest,
)

from ..scene import (
    NEW_STEP,
    Score,
    Snapshot,
    anchor_layout,
    build_engine,
    build_score,
    delete_entities,
    insert_note,
    layout,
    note_at,
    orphan_anchors,
    quarters,
    rest,
    rest_at,
    slot,
    snapshot,
)

# An anchor is storage shared by the rhythm and the contexts: a leaf and a clef starting at
# the same instant share it, and the orphan post reaps it only when neither holds it any
# more.

_Q: Fraction = Fraction(1, 4)


def _clef(*, score: Score, at: Fraction) -> ClefChange:
    """A bass clef asserted on the score's staff at a position of the first measure."""
    build_engine().process(
        document=score.document,
        requests=[
            CreateClefChangeRequest(
                measure=score.measures[0],
                position=MeasurePosition.of_fraction(fraction=at),
                staff=score.staff,
                clef=Clef.BASS,
            )
        ],
    )
    created: Context = score.staff.contexts[-1]
    assert isinstance(created, ClefChange)

    return created


@pytest.mark.unit
def test_deleting_a_note_keeps_its_anchor_for_the_clef_starting_there() -> None:
    """A quarter rest, then quarter notes, a clef on beat two. The rest and the note on beat
    two go in one batch and their hole is refilled with one half rest: nothing rhythmic
    starts on beat two any more, and its anchor stays only for the clef."""
    score: Score = build_score(measure_count=1)
    rest(score=score, parent=score.voice, at=Fraction(0), rhythmic_value=RhythmicValue.QUARTER)
    quarters(score=score, measure=0, beats=(1, 2, 3))
    clef: ClefChange = _clef(score=score, at=_Q)
    anchor: TemporalAnchor = clef.start

    delete_entities(
        score=score,
        entity_ids=[rest_at(score=score, at=Fraction(0)).id, note_at(score=score, at=_Q).id],
    )

    assert layout(score=score) == [
        slot(0, Fraction(0), Fraction(1, 2), "rest"),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert anchor in score.measures[0].anchors
    assert list(anchor.containers) == []
    assert list(anchor.starting_contexts) == [clef]
    assert anchor_layout(score=score) == [(0, Fraction(beat, 4)) for beat in range(4)]
    assert orphan_anchors(score=score) == []


@pytest.mark.unit
def test_the_orphan_post_spares_an_anchor_holding_only_a_clef() -> None:
    """A half over the first two quarters removes the leaf starting on beat two; the clef
    there still holds its anchor, so the post has nothing to reap."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    clef: ClefChange = _clef(score=score, at=_Q)

    insert_note(score=score, at=Fraction(0), rhythmic_value=RhythmicValue.HALF)

    assert layout(score=score) == [
        slot(0, Fraction(0), Fraction(1, 2), str(NEW_STEP)),
        slot(0, Fraction(1, 2), _Q, "0"),
        slot(0, Fraction(3, 4), _Q, "0"),
    ]
    assert clef.start in score.measures[0].anchors
    assert list(clef.start.containers) == []
    assert (
        OrphanAnchorsPostprocessor().search_fixes(
            document=score.document,
            geometry=ScoreGeometry(document=score.document),
        )
        == []
    )
    assert anchor_layout(score=score) == [(0, Fraction(beat, 4)) for beat in range(4)]


@pytest.mark.unit
def test_a_new_note_starts_at_the_anchor_a_clef_already_holds() -> None:
    """A clef in the middle of a half rest has an anchor of its own; an eighth inserted
    there starts at that anchor instead of a second one at the same instant."""
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0, beats=(0,))
    insert_note(score=score, at=_Q, rhythmic_value=RhythmicValue.QUARTER, step=1)
    clef: ClefChange = _clef(score=score, at=Fraction(5, 8))

    insert_note(score=score, at=Fraction(5, 8), rhythmic_value=RhythmicValue.EIGHTH)

    assert layout(score=score) == [
        slot(0, Fraction(0), _Q, "0"),
        slot(0, _Q, _Q, "1"),
        slot(0, Fraction(1, 2), Fraction(1, 8), "rest"),
        slot(0, Fraction(5, 8), Fraction(1, 8), str(NEW_STEP)),
        slot(0, Fraction(3, 4), _Q, "rest"),
    ]
    leaf = note_at(score=score, at=Fraction(5, 8)).note_carrier.owner
    assert isinstance(leaf, LeafRhythmicContainer)
    assert leaf.anchor is clef.start
    assert list(clef.start.starting_contexts) == [clef]
    assert anchor_layout(score=score) == [
        (0, Fraction(0)),
        (0, _Q),
        (0, Fraction(1, 2)),
        (0, Fraction(5, 8)),
        (0, Fraction(3, 4)),
    ]


@pytest.mark.unit
def test_deleting_a_clef_keeps_the_anchor_its_note_starts_at() -> None:
    score: Score = build_score(measure_count=1)
    quarters(score=score, measure=0)
    before: Snapshot = snapshot(score=score)
    clef: ClefChange = _clef(score=score, at=_Q)
    anchor: TemporalAnchor = clef.start

    build_engine().process(document=score.document, requests=[DeleteRequest(target=clef)])

    assert clef not in score.staff.contexts
    assert list(anchor.starting_contexts) == []
    assert anchor in score.measures[0].anchors
    assert snapshot(score=score) == before
