from fractions import Fraction

from tests.unit.domain.document_builders import anchor, note, score, size

from piano_app.application.use_cases.score.shared.view import ScoreView
from piano_app.domain.score.document.models.notation import RhythmicValue
from piano_app.domain.score.document.models.structural.rhythm import GroupRhythmicContainer


def test_nested_spaces_export_composed_geometry_and_voice() -> None:
    document = score()
    outer = GroupRhythmicContainer.create(
        parent=document.voices[1],
        anchor=anchor(document, Fraction(3, 4)),
        written_size=size(RhythmicValue.HALF, 3),
        occupied_size=size(RhythmicValue.WHOLE),
    )
    inner = GroupRhythmicContainer.create(
        parent=outer,
        anchor=anchor(document, Fraction(1)),
        written_size=size(RhythmicValue.EIGHTH, 3),
        occupied_size=size(RhythmicValue.QUARTER),
    )
    note(document, Fraction(1), voice=1, parent=inner)
    result = ScoreView(document=document).jsonify()["insertion_spaces"]
    assert result == [
        {
            "id": outer.id,
            "voice_id": document.voices[1].id,
            "parent_id": None,
            "start": {"numerator": 3, "denominator": 4},
            "scale": {"numerator": 2, "denominator": 3},
            "extent": {"numerator": 3, "denominator": 2},
        },
        {
            "id": inner.id,
            "voice_id": document.voices[1].id,
            "parent_id": outer.id,
            "start": {"numerator": 1, "denominator": 1},
            "scale": {"numerator": 4, "denominator": 9},
            "extent": {"numerator": 3, "denominator": 8},
        },
    ]


def test_score_without_groups_has_no_insertion_spaces() -> None:
    assert ScoreView(document=score()).jsonify()["insertion_spaces"] == []
