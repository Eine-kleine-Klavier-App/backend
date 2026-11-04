from fractions import Fraction

from piano_app.domain.score.document.models.notation import Articulation

# What share of its length a sound keeps under each mark of length; a carrier has at most one
# such mark, and a sound with none, a tenuto or a fermata keeps all of it. A slur changes
# nothing. These are defaults, a row to change (owner, 2026-11-07).
LENGTH_SHARES: dict[Articulation, Fraction] = {
    Articulation.STACCATO: Fraction(1, 2),
    Articulation.STACCATISSIMO: Fraction(1, 4),
    Articulation.TENUTO: Fraction(1),
    Articulation.FERMATA: Fraction(1),
}
