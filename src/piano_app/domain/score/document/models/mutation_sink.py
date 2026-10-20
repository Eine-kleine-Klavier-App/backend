from typing import Any, Protocol


class MutationSink(Protocol):
    """Port through which domain entities perform reversible mutations.

    It is intended to serve as a single mutation entry point to record all changes for
    undo and redo operations.
    """

    def set_field(self, target: object, field_name: str, value: object) -> None: ...

    def list_append(self, owner: object, field_name: str, item: Any) -> None: ...

    def list_insert(self, owner: object, field_name: str, index: int, item: Any) -> None: ...

    def list_remove(self, owner: object, field_name: str, item: Any) -> None: ...


class _DirectMutationSink:
    """Applies mutations immediately, recording nothing."""

    def set_field(self, target: object, field_name: str, value: object) -> None:
        setattr(target, field_name, value)

    def list_append(self, owner: object, field_name: str, item: Any) -> None:
        getattr(owner, field_name).append(item)

    def list_insert(self, owner: object, field_name: str, index: int, item: Any) -> None:
        getattr(owner, field_name).insert(index, item)

    def list_remove(self, owner: object, field_name: str, item: Any) -> None:
        getattr(owner, field_name).remove(item)


DIRECT_SINK: MutationSink = _DirectMutationSink()
