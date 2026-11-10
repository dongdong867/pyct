"""The kind of mapping each module of the target's package runs with as its builtins."""

from __future__ import annotations

from collections.abc import Mapping

# Python's own, which the target may replace in `builtins`
_issubclass, _type = issubclass, type


class PackageBuiltins(dict[str, object]):
    """The builtins each module of the target's package runs with
    (`pyct.intercept.wrap.LiveBuiltins`), told by kind whatever the target puts in
    `builtins`."""

    __slots__ = ()


def binds(builtins: Mapping[str, object]) -> bool:
    """Whether a module's builtins are the ones pyct binds, as each module of the target's
    package runs with, told by their type alone."""
    return _issubclass(_type(builtins), PackageBuiltins)
