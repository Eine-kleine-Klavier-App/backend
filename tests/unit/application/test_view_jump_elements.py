from fractions import Fraction
from typing import cast

from tests.unit.domain.document_builders import anchor

from piano_app.application.use_cases.score.shared import ScoreView
from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import NewFragment, Refrain, Volta


def _rows(*, document: ScoreDocument, kind: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = cast(
        list[dict[str, object]], ScoreView(document=document).jsonify()["contexts"]
    )
    return [row for row in rows if row["kind"] == kind]


def test_the_view_gives_a_refrain_its_end_and_how_many_times_it_is_played() -> None:
    document: ScoreDocument = ScoreDocument.create_fresh(
        voice_count=1, staff_count=1, measure_count=5
    )
    closed: Refrain = Refrain.create(
        start=anchor(document, Fraction(0)), end=anchor(document, Fraction(2)), times=3
    )
    Refrain.create(start=anchor(document, Fraction(3)), end=None, times=2)

    rows: list[dict[str, object]] = _rows(document=document, kind="refrain")

    by_id: dict[object, dict[str, object]] = {row["id"]: row for row in rows}
    assert by_id[closed.id]["times"] == 3
    assert by_id[closed.id]["end_measure_id"] == document.measures[2].id
    assert by_id[closed.id]["end_position"] == {"numerator": 0, "denominator": 1}
    assert [row["end_measure_id"] for row in rows if row["id"] != closed.id] == [None]


def test_the_view_gives_a_volta_its_body_end_its_fragments_and_the_number_of_passes() -> None:
    document: ScoreDocument = ScoreDocument.create_fresh(
        voice_count=1, staff_count=1, measure_count=7
    )
    Volta.create(
        start=anchor(document, Fraction(0)),
        body_end=anchor(document, Fraction(2)),
        fragments=[
            NewFragment(end=anchor(document, Fraction(3)), passes=frozenset({1, 3})),
            NewFragment(end=None, passes=frozenset({2})),
        ],
    )

    (row,) = _rows(document=document, kind="volta")

    assert row["body_end_measure_id"] == document.measures[2].id
    assert row["pass_count"] == 4
    assert row["fragments"] == [
        {
            "end_measure_id": document.measures[3].id,
            "end_position": {"numerator": 0, "denominator": 1},
            "passes": [1, 3],
        },
        {"end_measure_id": None, "end_position": None, "passes": [2]},
    ]
