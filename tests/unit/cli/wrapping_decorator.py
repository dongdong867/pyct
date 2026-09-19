"""A decorator, written here, that wraps a target written in another module.

``Number`` is a ``str`` here and an ``int`` in ``test_checks``, so the text
annotation ``inspect.signature`` reads through ``__wrapped__`` resolves to a
different plain type depending on which module's names read it.
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
