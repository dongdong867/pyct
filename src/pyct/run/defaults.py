"""The constructor parameters a seed leaves out under ``self``, filled with simple defaults."""

import inspect
from collections.abc import Mapping

from pyct.run.target import Target

# the defaults a left-out parameter is filled with, matched by exact type: values bind tracks
_SIMPLE: tuple[type, ...] = (int, float, str, bool)

# the parameters that gather what no other takes, which Python fills itself
_GATHERING = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)


def with_defaults(target: Target, seed: Mapping[str, object]) -> Mapping[str, object]:
    """The seed with each constructor parameter it leaves out under ``self`` filled.

    A parameter is filled when its default's type is exactly ``int``,
    ``float``, ``str`` or ``bool``, so the default is tracked like a value
    the seed gave and an input's line writes it. It goes after the keys the
    seed gave, in signature order. Any other default is left to Python. A
    target that builds no instance, a constructor Python could not read, or
    a value under ``self`` other than a dict leaves the seed as it came; the
    caller's seed is never changed.
    """
    name = target.self_name
    constructor = target.constructor
    fields = None if name is None else seed.get(name)
    if name is None or constructor is None or type(fields) is not dict:
        return seed
    given: dict[str, object] = dict(fields)
    for parameter in constructor.parameters.values():
        left_out = parameter.kind not in _GATHERING and parameter.name not in given
        if left_out and type(parameter.default) in _SIMPLE:
            given[parameter.name] = parameter.default
    return {**seed, name: given}
