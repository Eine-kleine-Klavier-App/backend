from fractions import Fraction

import pytest

from piano_app.domain.score.document.services.geometry import Transform


@pytest.mark.unit
def test_composing_a_chain_equals_walking_it_step_by_step() -> None:
    """The property the whole design rests on: affine composed with affine is affine,
    so a chain of frames collapses into one multiply-add."""
    inner: Transform = Transform(scale=Fraction(1, 2), offset=Fraction(1, 8))
    outer: Transform = Transform(scale=Fraction(2, 3), offset=Fraction(1, 4))

    composed: Transform = inner.then(outer)

    for value in (Fraction(0), Fraction(1, 3), Fraction(7, 5)):
        assert composed.apply_position(value) == outer.apply_position(inner.apply_position(value))
        assert composed.apply_length(value) == outer.apply_length(inner.apply_length(value))


@pytest.mark.unit
def test_inverse_undoes_the_step() -> None:
    """Descent is not a second implementation of the math — it is the inverse."""
    step: Transform = Transform(scale=Fraction(2, 3), offset=Fraction(1, 4))

    undone: Transform = step.then(step.inverse())

    assert undone.scale == Fraction(1)
    assert undone.offset == Fraction(0)


@pytest.mark.unit
def test_a_length_ignores_the_offset_but_a_position_does_not() -> None:
    """Point vs Duration in one assertion: the same squeeze at two places gives one
    length and two locations."""
    near: Transform = Transform.of_nesting(
        written=Fraction(3, 8), occupied=Fraction(1, 4), offset=Fraction(1, 4)
    )
    far: Transform = Transform.of_nesting(
        written=Fraction(3, 8), occupied=Fraction(1, 4), offset=Fraction(7, 8)
    )

    assert near.apply_length(Fraction(1, 8)) == far.apply_length(Fraction(1, 8))
    assert near.apply_position(Fraction(1, 8)) != far.apply_position(Fraction(1, 8))


@pytest.mark.unit
def test_nesting_squeezes_written_into_occupied() -> None:
    """A written eighth inside a triplet really lasts a twelfth of a whole."""
    triplet: Transform = Transform.of_nesting(
        written=Fraction(3, 8), occupied=Fraction(1, 4), offset=Fraction(1, 4)
    )

    assert triplet.apply_length(Fraction(1, 8)) == Fraction(1, 12)
    assert triplet.apply_position(Fraction(0)) == Fraction(1, 4)
    assert triplet.apply_position(Fraction(3, 8)) == Fraction(1, 2)


@pytest.mark.unit
def test_a_shift_never_compresses() -> None:
    """The measure case: a bar moves durations along the timeline, it does not
    rescale them."""
    shift: Transform = Transform.of_shift(offset=Fraction(3))

    assert shift.apply_length(Fraction(1, 4)) == Fraction(1, 4)
    assert shift.apply_position(Fraction(1, 4)) == Fraction(13, 4)


@pytest.mark.unit
def test_deep_nesting_stays_exact() -> None:
    """Fractions all the way down: composing does not drift."""
    step: Transform = Transform.of_nesting(
        written=Fraction(1, 4), occupied=Fraction(1, 6), offset=Fraction(1, 7)
    )

    chain: Transform = step.then(step).then(step)
    value: Fraction = Fraction(3, 11)

    assert chain.then(chain.inverse()).apply_position(value) == value


@pytest.mark.unit
@pytest.mark.parametrize("scale", [Fraction(0), Fraction(-1, 2)])
def test_rejects_a_scale_that_mirrors_or_collapses_the_space(scale: Fraction) -> None:
    with pytest.raises(ValueError, match="scale must be positive"):
        Transform(scale=scale, offset=Fraction(0))


@pytest.mark.unit
def test_rejects_nesting_with_no_written_room() -> None:
    with pytest.raises(ValueError, match="Written size must be positive"):
        Transform.of_nesting(written=Fraction(0), occupied=Fraction(1, 4), offset=Fraction(0))
