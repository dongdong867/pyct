"""What the ``*args`` and ``**kwargs`` tests share: a class a hint builds, the module its bare
name is read in, and a target for a function."""

import inspect

from pyct.run.target import Target

HOME = __name__


class Cart:
    def __init__(self, owner: str) -> None:
        self.owner = owner


def target_for(fn: object) -> Target:
    assert callable(fn)
    return Target(spec="m::f", fn=fn, file="m.py", signature=inspect.signature(fn))
