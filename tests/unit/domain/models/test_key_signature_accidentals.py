from fractions import Fraction

import pytest

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.context import (
    KEY_SIGNATURE_ACCIDENTALS,
    NO_ACCIDENTALS,
    KeySignatureChange,
)
from piano_app.domain.score.document.models.notation import Accidental

from ..document_builders import anchor, score


@pytest.mark.unit
def test_a_key_signature_holds_flats_naturals_and_sharps_only() -> None:
    assert {Accidental.FLAT, Accidental.NATURAL, Accidental.SHARP} == KEY_SIGNATURE_ACCIDENTALS


@pytest.mark.unit
@pytest.mark.parametrize("double", [Accidental.DOUBLE_SHARP, Accidental.DOUBLE_FLAT])
def test_a_key_signature_refuses_a_double_accidental(double: Accidental) -> None:
    document: ScoreDocument = score()

    with pytest.raises(ValueError, match="no double accidentals"):
        KeySignatureChange.create(
            start=anchor(document, Fraction(1)),
            staff=document.staffs[0],
            alterations=(double, *NO_ACCIDENTALS[1:]),
        )
