"""Public names at the edges of what sweep reads, for ``test_entries``."""

import types

from tests.unit.sweep.factory import Base, make_class

# a name the module lacks, and one whose lookup raises, are no entry
__all__ = [
    "missing",  # noqa: F822
    "lazy",  # noqa: F822
    7,
    "total",
    "alias",
    "renamed",
    "Built",
    "Moved",
    "Ghost",
    "looped",
    "foreign",
]


def total(n: int) -> int:
    return n


alias = total


def original(n: int) -> int:
    return n


renamed = original
del original

Built = make_class()


class Moved:
    def shift(self, n: int) -> int:
        return n


# a library may rename where a class says it lives; its own code still says where it is
Moved.__module__ = "tests.unit.sweep.factory"


class Ghost(Base):
    pass


Ghost.__module__ = "nowhere"


def looped(n: int) -> int:
    return n


looped.__wrapped__ = looped  # pyrefly: ignore[missing-attribute]

_compiled = compile("def f(n):\n    return n\n", "<string>", "exec")
_code = next(c for c in _compiled.co_consts if isinstance(c, types.CodeType))
foreign = types.FunctionType(_code, {"__name__": "elsewhere"}, "foreign")


def __getattr__(name: str) -> object:
    if name == "lazy":
        raise RuntimeError("made on first use, and making it fails")
    raise AttributeError(name)
