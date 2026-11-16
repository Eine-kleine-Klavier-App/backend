from fractions import Fraction

from tests.unit.domain.document_builders import note, score

from piano_app.application.use_cases.score.shared import ScoreView
from piano_app.domain.score.document.models.notation import (
    Accidental,
    DottedRhythmicValue,
    GlissandoType,
    GracePlacement,
    GraceType,
    RhythmicValue,
)
from piano_app.domain.score.document.models.relations import Glissando
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import AddGraceNoteIntent


def test_view_shows_a_glissando_between_two_notes() -> None:
    document = score()
    first = note(document, Fraction(0))
    second = note(document, Fraction(1, 4))
    relation = Glissando.create(
        start_note=first, end_note=second, glissando_type=GlissandoType.WAVY
    )

    view = ScoreView(document=document).jsonify()

    row = next(row for row in view["relations"] if row["id"] == relation.id)
    assert row == {
        "id": relation.id,
        "kind": "glissando",
        "start_note_id": first.id,
        "end_note_id": second.id,
        "glissando_type": "wavy",
    }


def test_view_shows_a_relation_that_only_grace_notes_carry() -> None:
    document = score()
    host = note(document, Fraction(0), value=RhythmicValue.HALF)
    for _ in range(2):
        intent = AddGraceNoteIntent(
            host_carrier_id=host.note_carrier.id,
            placement=GracePlacement.BEFORE,
            grace_type=GraceType.APPOGGIATURA,
            written_value=DottedRhythmicValue(value=RhythmicValue.EIGHTH),
            staff_id=document.staffs[0].id,
            staff_step=2,
            accidental=Accidental.NATURAL,
        )
        build_engine().process(
            document=document,
            requests=build_compiler().compile(document=document, intent=intent),
        )
    leaf = host.note_carrier.owner
    first, second = (item.carrier.notes[0] for item in leaf.grace_before.grace_items)
    relation = Glissando.create(
        start_note=first, end_note=second, glissando_type=GlissandoType.STRAIGHT
    )

    view = ScoreView(document=document).jsonify()

    assert relation.id in {row["id"] for row in view["relations"]}
