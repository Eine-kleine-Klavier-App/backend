import json
from typing import Any


def as_stored(record: dict[str, Any]) -> dict[str, Any]:
    """The record as a JSONB column gives it back: the keys of every object sorted, so nothing
    may depend on the order of keys."""
    return json.loads(json.dumps(record, sort_keys=True))
