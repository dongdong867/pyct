"""The objects each call builds before it calls the target."""

from __future__ import annotations

import inspect
from dataclasses import dataclass


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
