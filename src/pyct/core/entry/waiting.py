"""What the hooks around a piece of the target's code share (`pyct.core.entry.pieces`,
`pyct.core.entry.in_use`): a table of runs waiting on their end, and a value's JSON text."""

from __future__ import annotations

import json

from pyct.core.entry.plain_json import plain_json

# a run waiting on its end, by its frame's id and its column
type Key = tuple[int, int]
# each run waiting on its end, by its line, then by its key
type Waiting[Run] = dict[int, dict[Key, Run]]

_dumps = json.dumps


def popped[Run](waiting: Waiting[Run], line: int, key: Key) -> Run | None:
    """Take the run waiting at the line by the key out of the table, and hand it back."""
    at_line = waiting.get(line)
    if at_line is None:
        return None
    run = at_line.pop(key, None)
    if not at_line:
        del waiting[line]
    return run


def json_text(value: object, most: int | None = None) -> str | None:
    """The value's JSON text, or None when it is not plain JSON data (`plain_json`), a tuple not
    being such data, or, with ``most``, when its text is not shorter than ``most`` characters."""
    try:
        text = _dumps(plain_json(value, tuples=False, most=most))
    except (TypeError, ValueError, RecursionError):
        return None
    return text if most is None or len(text) < most else None
