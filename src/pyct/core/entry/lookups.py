"""An index read the target writes, ``x[k]``, which `pyct.intercept` hands here as
``__pyct_item__(x, k)``.

`item` is a router: it runs Python's own read, and none of the target's
code in its own lines, so blame reads through its frame (`PASSING`): a raise
under it, from Python's read or from the target's own `__getitem__`, is the
target's.
"""

from __future__ import annotations

import types


def item(container: object, key: object) -> object:
    """``container[key]``, as Python reads it."""
    return container[key]  # pyrefly: ignore[bad-index]


# the frames blame reads through
PASSING: frozenset[types.CodeType] = frozenset({item.__code__})
