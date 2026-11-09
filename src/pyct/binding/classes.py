"""A class a seed names, and its constructor's signature."""

from __future__ import annotations

import inspect
from typing import TypeGuard


def is_a_class(owner: object) -> TypeGuard[type]:
    """Whether ``owner`` is a class, told by its type alone: ``isinstance`` would read
    ``__class__``, which an object's own property can answer."""
    return issubclass(type(owner), type)


def constructor(cls: type) -> inspect.Signature | None:
    """The class's signature, or None when Python cannot read it.

    Reading it can run the class's own code, as a target's signature can,
    so any Exception or a SystemExit means the same: no signature to read.
    """
    try:
        return inspect.signature(cls)
    except (Exception, SystemExit):
        return None
