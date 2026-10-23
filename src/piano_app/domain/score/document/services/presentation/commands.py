from dataclasses import dataclass

from piano_app.domain.score.document.models.notation.stem import StemDirection
from piano_app.domain.score.document.models.presentation import (
    EndpointOffsets,
    HorizontalEndpointOffsets,
    HorizontalOffset,
    PresentationTarget,
    VerticalOffset,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class SetVerticalOffset:
    target: PresentationTarget
    value: VerticalOffset | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SetEndpointOffsets:
    target: PresentationTarget
    value: EndpointOffsets | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SetDirection:
    target: PresentationTarget
    value: StemDirection | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SetHorizontalOffset:
    target: PresentationTarget
    value: HorizontalOffset | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SetHorizontalEndpointOffsets:
    target: PresentationTarget
    value: HorizontalEndpointOffsets | None


type PresentationCommand = (
    SetVerticalOffset
    | SetEndpointOffsets
    | SetDirection
    | SetHorizontalOffset
    | SetHorizontalEndpointOffsets
)
