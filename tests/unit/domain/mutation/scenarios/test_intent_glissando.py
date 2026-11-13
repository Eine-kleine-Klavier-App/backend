from fractions import Fraction

import pytest
from tests.unit.domain.document_builders import note, score

from piano_app.domain.score.document.models.notation import GlissandoType
from piano_app.domain.score.document.models.relations import Glissando
from piano_app.domain.score.document.services.mutation import build_compiler, build_engine
from piano_app.domain.score.document.services.mutation.compiler import GlissandoNotesIntent
from piano_app.domain.score.document.services.mutation.instructions import MutationRejectedError

_Q: Fraction = Fraction(1, 4)


def _glissando(document, start, end) -> None:
    intent = GlissandoNotesIntent(
        start_note_id=start.id, end_note_id=end.id, glissando_type=GlissandoType.WAVY
    )
    build_engine().process(
        document=document, requests=build_compiler().compile(document=document, intent=intent)
    )


def test_a_glissando_joins_two_neighbouring_notes_with_its_type() -> None:
    document = score()
    first = note(document, Fraction(0), step=-2)
    second = note(document, _Q, step=3)

    _glissando(document, first, second)

    (relation,) = [r for r in first.relations if isinstance(r, Glissando)]
    assert relation.start is first and relation.end is second
    assert relation.glissando_type is GlissandoType.WAVY
    assert relation in second.relations


def test_a_glissando_from_a_step_to_itself_is_refused() -> None:
    document = score()
    first = note(document, Fraction(0), step=-2)
    second = note(document, _Q, step=-2)

    with pytest.raises(MutationRejectedError, match="two different steps"):
        _glissando(document, first, second)

    assert not first.relations


def test_a_glissando_between_notes_that_do_not_touch_is_refused() -> None:
    document = score()
    first = note(document, Fraction(0), step=-2)
    note(document, _Q, step=0)
    far = note(document, 2 * _Q, step=3)

    with pytest.raises(MutationRejectedError, match="touch in one voice"):
        _glissando(document, first, far)

    assert not first.relations


def test_a_note_starts_one_glissando_only() -> None:
    document = score()
    first = note(document, Fraction(0), step=-2)
    second = note(document, _Q, step=3)
    _glissando(document, first, second)

    with pytest.raises(MutationRejectedError, match="already starts"):
        _glissando(document, first, second)
