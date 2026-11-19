"""What one gesture changed in a record, and how to take it back or apply it again.

A record keeps its rows in ``tables``, each a mapping from a row's id to the row, and everything
else (the music revision, the order of the measures …) as plain fields. A change names what differs:

    {"fields": {name: [before, after] | {"removed": [[index, id]], "inserted": [[index, id]]}},
     "tables": {table: {row_id: [before_row, after_row]}}}

A row that did not exist has ``None`` on that side. Only what differs is written, so the change a
note's pitch makes is the one row of that note. A field that is a list of ids (the order of the
measures, the relations …) is written as what left it, with the place it had, and what came into
it, with the place it has: taking a relation out of seven hundred costs one id, not two lists of
seven hundred. Records are never modified in place: applying a change gives a new record that
shares every row it did not touch.
"""

from bisect import bisect_left
from typing import TypeGuard

from piano_app.application.ports.score import DocumentRecord, RecordChange

_FIELDS: str = "fields"
_TABLES: str = "tables"
_REMOVED: str = "removed"
_INSERTED: str = "inserted"


def diff_records(*, before: DocumentRecord, after: DocumentRecord) -> RecordChange:
    """The change that turns ``before`` into ``after``."""
    fields: dict[str, list[object] | dict[str, list[list[object]]]] = {
        name: _field_change(before=before.get(name), after=after.get(name))
        for name in sorted(before.keys() | after.keys())
        if name != _TABLES and before.get(name) != after.get(name)
    }

    tables: dict[str, dict[str, list[object]]] = {}
    before_tables: dict[str, dict[str, object]] = before.get(_TABLES, {})
    after_tables: dict[str, dict[str, object]] = after.get(_TABLES, {})
    for table in sorted(before_tables.keys() | after_tables.keys()):
        old_rows: dict[str, object] = before_tables.get(table, {})
        new_rows: dict[str, object] = after_tables.get(table, {})

        rows: dict[str, list[object]] = {}
        for row_id, row in new_rows.items():
            old_row: object | None = old_rows.get(row_id)
            if old_row != row:
                rows[row_id] = [old_row, row]

        for row_id, old_row in old_rows.items():
            if row_id not in new_rows:
                rows[row_id] = [old_row, None]

        if rows:
            tables[table] = rows

    change: RecordChange = {}
    if fields:
        change[_FIELDS] = fields

    if tables:
        change[_TABLES] = tables

    return change


def inverted(*, change: RecordChange) -> RecordChange:
    """The change that takes ``change`` back: what it turned into what, the other way round."""
    fields: dict[str, object] = {}
    for name, field_change in change.get(_FIELDS, {}).items():
        if isinstance(field_change, dict):
            fields[name] = {
                _REMOVED: field_change[_INSERTED],
                _INSERTED: field_change[_REMOVED],
            }
        else:
            fields[name] = [field_change[1], field_change[0]]

    tables: dict[str, dict[str, list[object]]] = {
        table: {row_id: [pair[1], pair[0]] for row_id, pair in rows.items()}
        for table, rows in change.get(_TABLES, {}).items()
    }

    result: RecordChange = {}
    if fields:
        result[_FIELDS] = fields

    if tables:
        result[_TABLES] = tables

    return result


def apply_change(*, record: DocumentRecord, change: RecordChange, forward: bool) -> DocumentRecord:
    """The record after ``change`` is applied (``forward``) or taken back."""
    side: int = 1 if forward else 0

    result: DocumentRecord = dict(record)
    for name, field_change in change.get(_FIELDS, {}).items():
        value: object | None
        if isinstance(field_change, dict):
            value = _apply_list_change(
                name=name, items=record.get(name), change=field_change, forward=forward
            )
        else:
            value = field_change[side]

        if value is None:
            result.pop(name, None)
        else:
            result[name] = value

    tables: dict[str, dict[str, object]] = dict(record.get(_TABLES, {}))
    for table, rows in change.get(_TABLES, {}).items():
        merged: dict[str, object] = dict(tables.get(table, {}))
        for row_id, pair in rows.items():
            row: object | None = pair[side]
            if row is None:
                merged.pop(row_id, None)
            else:
                merged[row_id] = row

        # a table the record did not have stays out unless a row is put in it
        if merged or table in tables:
            tables[table] = merged

    result[_TABLES] = tables

    return result


def _field_change(*, before: object, after: object) -> list[object] | dict[str, list[list[object]]]:
    """How one field differs: a pair, or, for a list of ids on both sides, what left and came in."""
    if _is_list_of_ids(before) and _is_list_of_ids(after):
        return _list_change(before=before, after=after)

    return [before, after]


def _is_list_of_ids(value: object) -> TypeGuard[list[str]]:
    # an id is a string and is in a list once: a list that is not that is written whole
    return (
        isinstance(value, list)
        and all(isinstance(item, str) for item in value)
        and len(set(value)) == len(value)
    )


def _list_change(*, before: list[str], after: list[str]) -> dict[str, list[list[object]]]:
    """What leaves ``before`` and what comes into ``after`` to make one of the other.

    What stays is the longest run of ids that comes in the same order in both lists, so an id
    that only moved is written as leaving and coming in, and the rest is not written.
    """
    place: dict[str, int] = {item: index for index, item in enumerate(before)}

    # the longest increasing run of the places the ids of ``after`` had in ``before``
    ends: list[int] = []
    ends_at: list[int] = []
    link: dict[int, int | None] = {}
    for index, item in enumerate(after):
        if item not in place:
            continue

        length: int = bisect_left(ends, place[item])
        link[index] = ends_at[length - 1] if length > 0 else None
        if length == len(ends):
            ends.append(place[item])
            ends_at.append(index)
        else:
            ends[length] = place[item]
            ends_at[length] = index

    stays: set[str] = set()
    last: int | None = ends_at[-1] if ends_at else None
    while last is not None:
        stays.add(after[last])
        last = link[last]

    return {
        _REMOVED: [[index, item] for index, item in enumerate(before) if item not in stays],
        _INSERTED: [[index, item] for index, item in enumerate(after) if item not in stays],
    }


def _apply_list_change(
    *,
    name: str,
    items: object,
    change: dict[str, list[list[object]]],
    forward: bool,
) -> list[str]:
    """The list after the change is applied (``forward``) or taken back: what leaves is taken
    out by its id, then what comes in is put at its place, from the first place to the last."""
    leaves: list[list[object]] = change[_REMOVED if forward else _INSERTED]
    comes: list[list[object]] = change[_INSERTED if forward else _REMOVED]
    if not isinstance(items, list):
        raise ValueError(f"The change of {name!r} is a change of a list, and the record has none.")

    going: set[object] = {item for _, item in leaves}
    result: list[str] = [item for item in items if item not in going]
    if len(items) - len(result) != len(leaves):
        raise ValueError(f"The change of {name!r} takes out ids the record does not hold.")

    placed: list[tuple[int, str]] = []
    for index, item in comes:
        if not isinstance(index, int) or not isinstance(item, str):
            raise ValueError(f"The change of {name!r} is not made of places and ids.")

        placed.append((index, item))

    for index, item in sorted(placed):
        if not 0 <= index <= len(result):
            raise ValueError(f"The change of {name!r} puts an id where the list has no place.")

        result.insert(index, item)

    return result
