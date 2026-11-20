import json
from fractions import Fraction
from typing import Any

import pytest
from tests.unit.domain.scene import Score, anchor_at, build_score, eighth_triplet, note_at, quarters

from piano_app.application.use_cases.score.shared import ScoreView
from piano_app.domain.score.document.models.context import Refrain, SustainHold
from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    GracePlacement,
    GraceType,
    RhythmicValue,
)
from piano_app.domain.score.document.models.relations import Tie
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import AddGraceNoteIntent

# The view cut by measure is the whole view: the header and the shares of all measures, put
# together in the order of the measures, give back every row of `jsonify`.


def _every_kind() -> Score:
    """A tie over the barline, a triplet, a pedal over the barline, a repeat and a grace note."""
    score: Score = build_score(measure_count=3)
    quarters(score=score, measure=0)
    quarters(score=score, measure=1, beats=(0, 1))
    Tie.create(
        start_note=note_at(score=score, at=Fraction(3, 4)),
        end_note=note_at(score=score, at=Fraction(1)),
    )
    eighth_triplet(score=score, parent=score.voice, at=Fraction(2))
    SustainHold.create(
        start=anchor_at(score=score, at=Fraction(1, 2)),
        end=anchor_at(score=score, at=Fraction(3, 2)),
    )
    Refrain.create(
        start=anchor_at(score=score, at=Fraction(0)),
        end=anchor_at(score=score, at=Fraction(2)),
        times=2,
    )
    intent = AddGraceNoteIntent(
        host_carrier_id=note_at(score=score, at=Fraction(1, 4)).note_carrier.id,
        placement=GracePlacement.BEFORE,
        grace_type=GraceType.APPOGGIATURA,
        written_value=DottedRhythmicValue(value=RhythmicValue.EIGHTH),
        staff_id=score.staff.id,
        staff_step=2,
        accidental=Accidental.SHARP,
    )
    build_engine().process(
        document=score.document,
        requests=build_compiler().compile(document=score.document, intent=intent),
    )

    return score


def _put_together(*, view: ScoreView, score: Score) -> dict[str, Any]:
    """The whole view as a client puts it together from the header and the measures."""
    header: dict[str, Any] = view.header_json()
    shares: list[dict[str, Any]] = [
        view.measure_json(measure=measure) for measure in score.document.measures
    ]
    roots: dict[str, list[str]] = {voice_id: [] for voice_id in header["voice_ids"]}
    for share in shares:
        for root in share["voice_roots"]:
            roots[root["voice_id"]].extend(root["rhythmic_container_ids"])

    presentation: dict[str, list[Any]] = {
        kind: list(rows) for kind, rows in header["presentation"].items()
    }
    for share in shares:
        for kind, rows in share["presentation"].items():
            presentation[kind].extend(rows)

    def joined(key: str) -> list[Any]:
        return [row for share in shares for row in share[key]]

    return {
        "music_revision": header["music_revision"],
        "presentation": presentation,
        "presentation_capabilities": [
            *header["presentation_capabilities"],
            *joined("presentation_capabilities"),
        ],
        "insertion_spaces": joined("insertion_spaces"),
        "staffs": header["staffs"],
        "measures": [share["measure"] for share in shares],
        "voices": [
            {"id": voice_id, "rhythmic_container_ids": container_ids}
            for voice_id, container_ids in roots.items()
        ],
        "rhythmic_containers": joined("rhythmic_containers"),
        "carriers": joined("carriers"),
        "items": joined("items"),
        "relations": joined("relations"),
        "contexts": joined("contexts"),
    }


def _unordered(rows: list[Any]) -> list[str]:
    """Rows of a list compared whatever measure they came with."""
    return sorted(json.dumps(row, sort_keys=True) for row in rows)


@pytest.mark.unit
def test_the_header_and_every_measure_give_back_the_whole_view() -> None:
    score: Score = _every_kind()
    view: ScoreView = ScoreView(document=score.document)

    whole: dict[str, Any] = view.jsonify()
    together: dict[str, Any] = _put_together(view=view, score=score)

    assert together.keys() == whole.keys()
    for key in ("music_revision", "staffs", "measures", "voices"):
        assert together[key] == whole[key], key
    for key in (
        "presentation_capabilities",
        "insertion_spaces",
        "rhythmic_containers",
        "carriers",
        "items",
        "relations",
        "contexts",
    ):
        assert _unordered(together[key]) == _unordered(whole[key]), key
    for kind, rows in whole["presentation"].items():
        assert _unordered(together["presentation"][kind]) == _unordered(rows), kind


@pytest.mark.unit
def test_a_tie_over_the_barline_is_kept_with_the_measure_of_its_first_note() -> None:
    score: Score = _every_kind()
    view: ScoreView = ScoreView(document=score.document)
    first, second, _ = score.document.measures

    first_share: dict[str, Any] = view.measure_json(measure=first)
    in_first = {row["kind"] for row in first_share["relations"]}
    in_second = view.measure_json(measure=second)["relations"]

    assert "tie" in in_first
    assert in_second == []
