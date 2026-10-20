from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from piano_app.domain.score.document.models.mutation_sink import DIRECT_SINK, MutationSink
from piano_app.domain.score.document.models.notation.stem import StemDirection

from .targets import PresentationTarget
from .values import (
    EndpointOffsets,
    HorizontalEndpointOffsets,
    HorizontalOffset,
    VerticalOffset,
)


@dataclass(slots=True, kw_only=True)
class Presentation:
    _vertical: dict[PresentationTarget, VerticalOffset] = field(default_factory=dict)
    _endpoints: dict[PresentationTarget, EndpointOffsets] = field(default_factory=dict)
    _directions: dict[PresentationTarget, StemDirection] = field(default_factory=dict)
    _horizontal: dict[PresentationTarget, HorizontalOffset] = field(default_factory=dict)
    _horizontal_endpoints: dict[PresentationTarget, HorizontalEndpointOffsets] = field(
        default_factory=dict
    )

    @property
    def vertical(self) -> Mapping[PresentationTarget, VerticalOffset]:
        return MappingProxyType(self._vertical)

    @property
    def endpoints(self) -> Mapping[PresentationTarget, EndpointOffsets]:
        return MappingProxyType(self._endpoints)

    @property
    def directions(self) -> Mapping[PresentationTarget, StemDirection]:
        return MappingProxyType(self._directions)

    @property
    def horizontal(self) -> Mapping[PresentationTarget, HorizontalOffset]:
        return MappingProxyType(self._horizontal)

    @property
    def horizontal_endpoints(self) -> Mapping[PresentationTarget, HorizontalEndpointOffsets]:
        return MappingProxyType(self._horizontal_endpoints)

    def set_vertical(
        self,
        *,
        target: PresentationTarget,
        value: VerticalOffset | None,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        updated = dict(self._vertical)
        updated.pop(target, None)
        if value is not None:
            updated[target] = value
        sink.set_field(self, "_vertical", updated)

    def set_endpoints(
        self,
        *,
        target: PresentationTarget,
        value: EndpointOffsets | None,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        updated = dict(self._endpoints)
        updated.pop(target, None)
        if value is not None:
            updated[target] = value
        sink.set_field(self, "_endpoints", updated)

    def set_direction(
        self,
        *,
        target: PresentationTarget,
        value: StemDirection | None,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        updated = dict(self._directions)
        updated.pop(target, None)
        if value is not None:
            updated[target] = value
        sink.set_field(self, "_directions", updated)

    def set_horizontal(
        self,
        *,
        target: PresentationTarget,
        value: HorizontalOffset | None,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        updated = dict(self._horizontal)
        updated.pop(target, None)
        if value is not None:
            updated[target] = value
        sink.set_field(self, "_horizontal", updated)

    def set_horizontal_endpoints(
        self,
        *,
        target: PresentationTarget,
        value: HorizontalEndpointOffsets | None,
        sink: MutationSink = DIRECT_SINK,
    ) -> None:
        updated = dict(self._horizontal_endpoints)
        updated.pop(target, None)
        if value is not None:
            updated[target] = value
        sink.set_field(self, "_horizontal_endpoints", updated)
