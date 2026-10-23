from collections.abc import Sequence

from piano_app.domain.score.document.models import ScoreDocument
from piano_app.domain.score.document.models.mutation_sink import MutationSink
from piano_app.domain.score.document.models.presentation import (
    DirectedPlacement,
    EndpointPlacement,
    HorizontalEndpointPlacement,
    HorizontalPlacement,
    VerticalPlacement,
)

from .capabilities import presentation_capabilities
from .commands import (
    PresentationCommand,
    SetDirection,
    SetEndpointOffsets,
    SetHorizontalEndpointOffsets,
    SetHorizontalOffset,
    SetVerticalOffset,
)


def _is_factor(command: PresentationCommand) -> bool:
    """Whether a vertical or endpoint value of a scaled target is above zero; a value that is
    taken away, a direction and the sideways values say nothing about the scale."""
    if isinstance(command, SetVerticalOffset):
        return command.value is None or command.value.value > 0

    if isinstance(command, SetEndpointOffsets):
        return command.value is None or (command.value.left > 0 and command.value.right > 0)

    return True


class PresentationEditor:
    def apply(
        self,
        *,
        document: ScoreDocument,
        commands: Sequence[PresentationCommand],
        sink: MutationSink,
    ) -> None:
        capabilities = presentation_capabilities(document=document)
        for command in commands:
            capability = capabilities.get(command.target)
            allowed = capability is not None and (
                (isinstance(command, SetVerticalOffset) and capability.vertical)
                or (isinstance(command, SetEndpointOffsets) and capability.endpoints)
                or (isinstance(command, SetDirection) and capability.directed)
                or (isinstance(command, SetHorizontalOffset) and capability.horizontal)
                or (
                    isinstance(command, SetHorizontalEndpointOffsets)
                    and capability.horizontal_endpoints
                )
            )
            if capability is None or not allowed:
                raise ValueError("Presentation capability is unavailable for this target.")
            if capability.scaled and not _is_factor(command):
                raise ValueError("A scaled placement is a factor above zero.")
        vertical: VerticalPlacement = document.presentation
        endpoints: EndpointPlacement = document.presentation
        directed: DirectedPlacement = document.presentation
        horizontal: HorizontalPlacement = document.presentation
        horizontal_endpoints: HorizontalEndpointPlacement = document.presentation
        for command in commands:
            if isinstance(command, SetVerticalOffset):
                vertical.set_vertical(target=command.target, value=command.value, sink=sink)
            elif isinstance(command, SetEndpointOffsets):
                endpoints.set_endpoints(target=command.target, value=command.value, sink=sink)
            elif isinstance(command, SetHorizontalOffset):
                horizontal.set_horizontal(target=command.target, value=command.value, sink=sink)
            elif isinstance(command, SetHorizontalEndpointOffsets):
                horizontal_endpoints.set_horizontal_endpoints(
                    target=command.target, value=command.value, sink=sink
                )
            else:
                directed.set_direction(target=command.target, value=command.value, sink=sink)

    def prune(self, *, document: ScoreDocument, sink: MutationSink) -> None:
        capabilities = presentation_capabilities(document=document)
        presentation = document.presentation
        for target in tuple(presentation.vertical):
            if target not in capabilities or not capabilities[target].vertical:
                presentation.set_vertical(target=target, value=None, sink=sink)
        for target in tuple(presentation.endpoints):
            if target not in capabilities or not capabilities[target].endpoints:
                presentation.set_endpoints(target=target, value=None, sink=sink)
        for target in tuple(presentation.directions):
            if target not in capabilities or not capabilities[target].directed:
                presentation.set_direction(target=target, value=None, sink=sink)
        for target in tuple(presentation.horizontal):
            if target not in capabilities or not capabilities[target].horizontal:
                presentation.set_horizontal(target=target, value=None, sink=sink)
        for target in tuple(presentation.horizontal_endpoints):
            if target not in capabilities or not capabilities[target].horizontal_endpoints:
                presentation.set_horizontal_endpoints(target=target, value=None, sink=sink)
