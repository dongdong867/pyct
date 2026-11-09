"""The objects each call builds before it calls the target."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TypeGuard

# the key that names an object form's class, and the key of the items it passes by position
CLASS_KEY = "__class__"
ARGS_KEY = "__args__"


def object_form(value: object) -> TypeGuard[dict[str, object]]:
    """Whether ``value`` is an object form: exactly a ``dict``, holding ``"__class__"``.

    Whether one is built depends on its place too: the walk and the plan of a call each say
    where they look for one.
    """
    return type(value) is dict and CLASS_KEY in value


@dataclass(frozen=True)
class SelfBuild:
    """How each call builds the instance a method runs on.

    ``cls`` is the class the target's spec names before the method, and
    ``name`` the method's first parameter, the seed's key for the
    constructor's arguments. ``positional`` is the constructor's parameters
    each construction passes by position, read once at load.
    """

    cls: type
    name: str
    positional: tuple[inspect.Parameter, ...] = ()
