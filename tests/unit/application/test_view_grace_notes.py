from fractions import Fraction

from tests.unit.domain.document_builders import note, score

from piano_app.application.use_cases.score.shared import ScoreView
from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    GracePlacement,
    GraceType,
    RhythmicValue,
)
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import AddGraceNoteIntent


def test_view_shows_the_grace_groups_of_a_note_and_the_time_they_take() -> None:
    document = score()
    host = note(document, Fraction(0))
    for placement, kind, value in (
        (GracePlacement.BEFORE, GraceType.APPOGGIATURA, RhythmicValue.EIGHTH),
        (GracePlacement.AFTER, GraceType.ACCIACCATURA, RhythmicValue.SIXTEENTH),
    ):
        intent = AddGraceNoteIntent(
            host_carrier_id=host.note_carrier.id,
            placement=placement,
            grace_type=kind,
            written_value=DottedRhythmicValue(value=value),
            staff_id=document.staffs[0].id,
            staff_step=2,
            accidental=Accidental.SHARP,
        )
        build_engine().process(
            document=document, requests=build_compiler().compile(document=document, intent=intent)
        )

    view = ScoreView(document=document).jsonify()

    leaf = next(
        row for row in view["rhythmic_containers"] if row.get("carrier_id") == host.note_carrier.id
    )
    before, after = leaf["grace_before"], leaf["grace_after"]
    assert before["grace_type"] == "appoggiatura"
    assert after["grace_type"] == "acciaccatura"
    assert [item["rhythmic_value"] for item in before["items"]] == [{"value": 8, "dots": 0}]
    # an eighth as written, a slashed sixteenth a quarter of its length
    assert leaf["grace_taken"] == {"numerator": 9, "denominator": 64}

    carriers = {row["id"] for row in view["carriers"]}
    for item in (*before["items"], *after["items"]):
        assert item["carrier_id"] in carriers
    # the host and its two grace notes
    assert sum(row["kind"] == "note" for row in view["items"]) == 3


def test_view_of_a_note_without_grace_notes_has_none() -> None:
    document = score()
    host = note(document, Fraction(0))

    view = ScoreView(document=document).jsonify()

    leaf = next(
        row for row in view["rhythmic_containers"] if row.get("carrier_id") == host.note_carrier.id
    )
    assert leaf["grace_before"] is None
    assert leaf["grace_after"] is None
    assert leaf["grace_taken"] == {"numerator": 0, "denominator": 1}
