"""A number read out of a container, used as a position or a key by a list, a dict or a str.

Such an operation has no form for most tracked numbers, and on one it turns its receiver plain.
A float or a bool inside a container is tracked, so without this rule `ys[flags[0]]` would lose
every fork on `ys`. So the number reads as its plain value there, a downgrade names it, and the
receiver stays tracked. A fact keeps the number at that value, so an answer takes the path, and
an unsat with such a fact says nothing of another value (``solver.read_kinds``). A number the
input gave as a parameter is not read out of anything, and keeps the rule it always had.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from pyct.core.branch import KEPT, READ_HEADS, Downgrade, Expression, caller_site
from pyct.core.values import BASES, held, plain

# the heads of a read of a container
_READS = frozenset({"[]", *READ_HEADS.values()})

# the heads of a read that says it found a float or a bool
_SAID_NUMBERS = frozenset({READ_HEADS["float"], READ_HEADS["bool"]})

# the head of the int a float or a bool is, as `int(x)` or `x + 1` makes it
_THE_INT_OF = "int"


def _reads_any_of(form: Expression, heads: frozenset[str], whole: bool) -> bool:
    """Whether ``form`` holds a list headed by one of ``heads``, or, when ``whole``, the int of a
    read of a container."""
    stack = [form]
    seen: set[int] = set()
    while stack:
        part = stack.pop()
        if not isinstance(part, list) or not part or id(part) in seen:
            continue
        seen.add(id(part))
        head = part[0]
        if isinstance(head, str) and head in heads:
            return True
        if whole and head == _THE_INT_OF and _reads_any_of(part[1], _READS, False):
            return True
        stack.extend(part)
    return False


def _read_out_of_a_container(value: Any, base: type) -> bool:
    """Whether a tracked number comes from an item or a value inside an argument: a float or a
    bool that reads one, or an int made from a float or a bool that does."""
    if base is int:
        return _reads_any_of(value.expression, _SAID_NUMBERS, True)
    return _reads_any_of(value.expression, _READS, False)


def _settled(value: Any, name: str) -> Any:
    """``value`` as ``name`` takes it: its plain value, named, where it was read out of a
    container; a slice with each of its bounds so; anything else as it is."""
    if type(value) is slice:
        bounds = [_settled(bound, name) for bound in (value.start, value.stop, value.step)]
        return slice(*bounds)
    base = BASES.get(type(value))
    if base not in (int, bool, float) or not _read_out_of_a_container(value, base):
        return value
    bare: Any = plain(value, base)
    value.sink.append(Downgrade(name=name, site=caller_site()))
    if abs(bare) != float("inf") and bare == bare:
        held(value.sink, [KEPT, ["==", value.expression, bare]], True, name)
    return bare


def _reading_plain(method: Callable[..., Any], name: str, every: bool) -> Callable[..., Any]:
    """``method`` with its first argument settled, or each of them when ``every``."""

    def settle(self: object, /, *args: Any, **kwargs: Any) -> Any:
        if every:
            kept = [_settled(arg, name) for arg in args]
            given = {key: _settled(arg, name) for key, arg in kwargs.items()}
            return method(self, *kept, **given)
        if not args:
            return method(self, **kwargs)
        return method(self, _settled(args[0], name), *args[1:], **kwargs)

    return settle


def reads_plain(cls: type, names: Iterable[str], *, every: bool = False) -> None:
    """Have each of ``cls``'s operations take a number read out of a container as its plain value:
    its first argument, the one that is a position or a key, or each of them when ``every``."""
    for name in names:
        setattr(cls, name, _reading_plain(getattr(cls, name), name, every))
