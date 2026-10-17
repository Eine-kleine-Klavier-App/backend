from dataclasses import dataclass
from typing import TYPE_CHECKING

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.shared.abstract import abstract

from ..base import Context

if TYPE_CHECKING:
    from piano_app.domain.score.document.models.structural import Staff


@abstract
@dataclass(kw_only=True, eq=False)
class StaffScoped(Context):
    """Scope axis: a context tied to one staff.

    Orthogonal to the Point/Span form axis — combined with either via multiple
    inheritance between two dataclass role bases.
    """

    _staff: Staff

    @property
    def staff(self) -> Staff:
        return self._staff

    def attach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        super().attach(sink=sink)
        self.staff.add_context(context=self, sink=sink)

    def detach(self, *, sink: MutationSink = DIRECT_SINK) -> None:
        self.staff.remove_context(context=self, sink=sink)
        super().detach(sink=sink)
