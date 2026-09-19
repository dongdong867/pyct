"""A decorator, written here, that wraps a target written in another module.

``Number`` is a ``str`` here and an ``int`` in ``test_checks``, so a text
annotation spelling it means a different plain type in each of the two
modules a decorated target is written across.
"""

import functools
from collections.abc import Callable

# the name this module spells, which the wrapped target's text is not written against
Number = str


def wrapped_elsewhere(fn: Callable[..., object]) -> Callable[..., object]:
    """Wrap ``fn`` the usual way, so the wrapper carries this module's globals."""

    @functools.wraps(fn)
    def wrapper(*args: object, **kwargs: object) -> object:
        return fn(*args, **kwargs)

    return wrapper
