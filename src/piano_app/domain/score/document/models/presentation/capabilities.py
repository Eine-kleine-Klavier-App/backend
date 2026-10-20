from collections.abc import Mapping
from typing import Protocol

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.score.document.models.notation.stem import StemDirection

from .targets import PresentationTarget
from .values import (
    EndpointOffsets,
    HorizontalEndpointOffsets,
    HorizontalOffset,
    VerticalOffset,
)


class VerticalPlacement(Protocol):
    @property
    def vertical(self) -> Mapping[PresentationTarget, VerticalOffset]: ...

    def set_vertical(
        self,
        *,
        target: PresentationTarget,
        value: VerticalOffset | None,
        sink: MutationSink = DIRECT_SINK,
    ) -> None: ...


class EndpointPlacement(Protocol):
    @property
    def endpoints(self) -> Mapping[PresentationTarget, EndpointOffsets]: ...

    def set_endpoints(
        self,
        *,
        target: PresentationTarget,
        value: EndpointOffsets | None,
        sink: MutationSink = DIRECT_SINK,
    ) -> None: ...


class DirectedPlacement(Protocol):
    @property
    def directions(self) -> Mapping[PresentationTarget, StemDirection]: ...

    def set_direction(
        self,
        *,
        target: PresentationTarget,
        value: StemDirection | None,
        sink: MutationSink = DIRECT_SINK,
    ) -> None: ...


class HorizontalPlacement(Protocol):
    @property
    def horizontal(self) -> Mapping[PresentationTarget, HorizontalOffset]: ...

    def set_horizontal(
        self,
        *,
        target: PresentationTarget,
        value: HorizontalOffset | None,
        sink: MutationSink = DIRECT_SINK,
    ) -> None: ...


class HorizontalEndpointPlacement(Protocol):
    @property
    def horizontal_endpoints(self) -> Mapping[PresentationTarget, HorizontalEndpointOffsets]: ...

    def set_horizontal_endpoints(
        self,
        *,
        target: PresentationTarget,
        value: HorizontalEndpointOffsets | None,
        sink: MutationSink = DIRECT_SINK,
    ) -> None: ...
