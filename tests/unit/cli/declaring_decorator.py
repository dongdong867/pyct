"""A decorator, written here, that declares the signature it wants read.

``inspect.signature`` stops at a declared ``__signature__`` while
``inspect.unwrap`` walks straight past it, so the text below is written here
and the function underneath is written somewhere else. ``Number`` is a
``str`` here and an ``int`` in ``test_checks``; ``Elsewhere`` is spelled only
here.
"""

import functools
import inspect
from collections.abc import Callable, Mapping

# the name both modules spell, each meaning a different plain type
Number = str
# the name only this module spells
Elsewhere = str


def declares_its_signature(
    fn: Callable[..., object], annotations: Mapping[str, str]
) -> Callable[..., object]:
    """Wrap ``fn`` under a declared signature whose annotations are text written here."""

    @functools.wraps(fn)
    def wrapper(*args: object, **kwargs: object) -> object:
        return fn(*args, **kwargs)

    wrapper.__signature__ = inspect.Signature(  # pyrefly: ignore[missing-attribute]
        [
            inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=text)
            for name, text in annotations.items()
        ]
    )
    return wrapper
