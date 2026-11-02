from dataclasses import dataclass
from typing import Any, Protocol


class _JournalEntry(Protocol):
    def apply(self) -> None: ...  # redo: re-do the forward change

    def undo(self) -> None: ...  # undo: revert to the previous state


class ChangeListener(Protocol):
    """Told about each change right after the journal has recorded it."""

    def on_set(self, target: object, field_name: str) -> None: ...

    def on_list(self, owner: object, field_name: str, item: Any) -> None: ...


@dataclass(slots=True, kw_only=True)
class _SetField:
    target: object
    field_name: str
    previous_value: object
    new_value: object

    def apply(self) -> None:
        setattr(self.target, self.field_name, self.new_value)

    def undo(self) -> None:
        setattr(self.target, self.field_name, self.previous_value)


@dataclass(slots=True, kw_only=True)
class _ListInsert:
    owner: object
    field_name: str
    target: list[Any]
    index: int
    item: Any

    def apply(self) -> None:
        self.target.insert(self.index, self.item)

    def undo(self) -> None:
        del self.target[self.index]


@dataclass(slots=True, kw_only=True)
class _ListRemove:
    owner: object
    field_name: str
    target: list[Any]
    index: int
    item: Any

    def apply(self) -> None:
        del self.target[self.index]

    def undo(self) -> None:
        self.target.insert(self.index, self.item)


class MutationLog:
    """Append-only journal of state-changing primitives — reversible AND re-appliable.

    Each entry captures both directions: ``undo`` reverts to the previous state and
    ``apply`` re-does the forward change. So one journal serves three roles: the
    gesture's inverse (transaction abort / user undo) and its replay (redo), and, in
    time, the delta between two saved revisions. Handlers route every mutation through
    these primitives, so attach/detach are list inserts/removes and edits are field sets.
    """

    def __init__(self) -> None:
        self._entries: list[_JournalEntry] = []
        self._listeners: list[ChangeListener] = []

    @property
    def has_changes(self) -> bool:
        return bool(self._entries)

    def subscribe(self, listener: ChangeListener) -> None:
        """Tell ``listener`` of every change recorded from now on.

        It sees the model as the change left it. Rollback and reapply notify no one: an
        index lives for one transaction and is dropped with it.
        """
        self._listeners.append(listener)

    def set_field(self, target: object, field_name: str, value: object) -> None:
        if getattr(target, field_name) == value:
            return
        entry: _SetField = _SetField(
            target=target,
            field_name=field_name,
            previous_value=getattr(target, field_name),
            new_value=value,
        )
        entry.apply()
        self._entries.append(entry)
        for listener in self._listeners:
            listener.on_set(target, field_name)

    def list_append(self, owner: object, field_name: str, item: Any) -> None:
        target: list[Any] = getattr(owner, field_name)
        entry: _ListInsert = _ListInsert(
            owner=owner,
            field_name=field_name,
            target=target,
            index=len(target),
            item=item,
        )
        entry.apply()
        self._entries.append(entry)
        self._notify_list(owner=owner, field_name=field_name, item=item)

    def list_insert(self, owner: object, field_name: str, index: int, item: Any) -> None:
        target: list[Any] = getattr(owner, field_name)
        entry: _ListInsert = _ListInsert(
            owner=owner,
            field_name=field_name,
            target=target,
            index=index,
            item=item,
        )
        entry.apply()
        self._entries.append(entry)
        self._notify_list(owner=owner, field_name=field_name, item=item)

    def list_remove(self, owner: object, field_name: str, item: Any) -> None:
        target: list[Any] = getattr(owner, field_name)
        index: int = target.index(item)
        entry: _ListRemove = _ListRemove(
            owner=owner,
            field_name=field_name,
            target=target,
            index=index,
            item=item,
        )
        entry.apply()
        self._entries.append(entry)
        self._notify_list(owner=owner, field_name=field_name, item=item)

    def rollback(self) -> None:
        """Revert the journal (one gesture). Replay every entry's ``undo`` in reverse order.

        Used for a transaction abort (the failed gesture is then dropped) and for user
        undo (the journal is kept and moves to the redo stack).
        """
        for entry in reversed(self._entries):
            entry.undo()

    def reapply(self) -> None:
        """Re-do the journal (one gesture). Replay every entry's ``apply`` in original order."""
        for entry in self._entries:
            entry.apply()

    def _notify_list(self, *, owner: object, field_name: str, item: Any) -> None:
        for listener in self._listeners:
            listener.on_list(owner, field_name, item)
