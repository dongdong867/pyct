"""What `int(x)`, `float(x)` and `bool(x)` answer on a tracked value, where the code writes them.

Python's `int` and `float` copy whatever `__int__` or `__float__` hands back
into a plain number, read a str's text without calling any of its methods,
and `bool` tests its argument for truth on the spot, so a tracked value would
lose its condition in each. pyct substitutes a call written with one of these
names (`pyct.intercept`), and when the name holds Python's own and its one
argument is tracked, the answer comes from here:

- `int` of a tracked int, `float` of a tracked float and `bool` of a tracked
  bool is the value itself, and adds no node;
- `int` and `float` of a tracked bool are 1 or 0, and 1.0 or 0.0, carrying
  `["int", b]` and `["float", b]`; `float` of a tracked int carries
  `["float", n]`;
- `int` of a tracked float cuts it toward zero after its finite fork, as
  `math.trunc` does, carrying `["int", f]`;
- `int` and `float` of a tracked str first record whether Python reads the
  text as that number, `["isint", s]` or `["isfloat", s]`, taken true when
  it does, and then read it, carrying `["int", s]` or `["float", s]`; text
  Python refuses raises its ValueError past the fork;
- `bool` of a tracked number or str is a tracked bool holding the condition
  `if x:` tests, untested, so its fork is recorded where the target tests it.

`int(s, 16)`, and any other call of `int` on a tracked str pyct does not
encode, is Python's own answer and a downgrade named `int`. `map(int, ...)`
applies the same conversion to each item, lazily, as `map` does.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pyct.core import floats, numbers
from pyct.core.bools import ConcolicBool
from pyct.core.branch import Downgrade, Expression
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
from pyct.core.values import forked, own

# the tracked values a conversion takes as its one argument
_TRACKED = (ConcolicBool, ConcolicInt, ConcolicFloat, ConcolicStr)


def _reads(kind: type, text: str) -> bool:
    """Whether Python's own `int` or `float` reads the text as a number."""
    try:
        kind(text)
    except ValueError:
        return False
    return True


def _read(value: ConcolicStr, kind: type, check: str) -> Any:
    """A tracked str read as `kind`: the fork on whether Python reads it, then the number.

    The fork goes in before Python's own call, so the input it refuses lists
    the fork, taken false, beside the ValueError it raises (``README.md ›
    Rules › forks``). The text is read without any method of the tracked
    str, as Python reads it, so the message names the text as Python's does.
    """
    text = str.__str__(value)
    forked(value.sink, [check, value.expression], _reads(kind, text))
    return numbers.tracked(own(kind, text), [kind.__name__, value.expression], value.sink)


def int_of(value: object) -> Any:
    """`int(x)` on one tracked value."""
    if type(value) is ConcolicInt:
        return value
    if type(value) is ConcolicBool:
        return numbers.tracked(int.__index__(value), ["int", value.expression], value.sink)
    if type(value) is ConcolicFloat:
        return floats.truncated(value)
    return _read(_text(value), int, "isint")


def float_of(value: object) -> Any:
    """`float(x)` on one tracked value."""
    if type(value) is ConcolicFloat:
        return value
    if type(value) is ConcolicStr:
        return _read(value, float, "isfloat")
    number = _number(value)
    return numbers.tracked(own(int.__float__, number), ["float", number.expression], number.sink)


def bool_of(value: object) -> Any:
    """`bool(x)` on one tracked value: a tracked bool, its condition untested."""
    if type(value) is ConcolicBool:
        return value
    tracked = _tested(value)
    truth, false = _TRUTH[type(tracked)]
    expression = ["!=", tracked.expression, false]
    return ConcolicBool(own(truth, tracked), expression=expression, sink=tracked.sink)


def _filled(text: str) -> bool:
    """Whether a str holds any character, read without any method of a tracked one."""
    return str.__len__(text) > 0


# what `if x:` tests on each tracked type: its own truth, which is that x is not this value
_TRUTH: dict[type, tuple[Callable[[Any], bool], Expression]] = {
    ConcolicInt: (int.__bool__, 0),
    ConcolicFloat: (float.__bool__, 0.0),
    ConcolicStr: (_filled, "''"),
}


def int_in_another_form(*args: object, **kwargs: object) -> object:
    """`int` on a tracked str in a form pyct does not encode, `int(s, 16)` say: a downgrade.

    Python's own answer, and a note that the condition was lost, after the
    call, so a call that raises records nothing.
    """
    answer = own(int, *args, **kwargs)
    _text(args[0]).sink.append(Downgrade(name="int"))
    return answer


# each conversion, by the builtin it stands for
_CONVERSIONS: tuple[tuple[type, Callable[[object], Any]], ...] = (
    (int, int_of),
    (float, float_of),
    (bool, bool_of),
)


def picked(
    callee: object, args: tuple[object, ...], kwargs: dict[str, object]
) -> Callable[..., Any] | None:
    """What answers a call of ``callee`` on these arguments in Python's place, or None for Python.

    ``callee`` is what the name the code wrote holds when the call runs, so a
    name the target binds to its own function keeps the target's meaning.
    Only identities and types are read, so nothing of the target's runs here.
    """
    if callee is map:
        return _mapped(args)
    for builtin, conversion in _CONVERSIONS:
        if callee is builtin:
            return _picked_for(builtin, conversion, args, kwargs)
    return None


def _picked_for(
    builtin: type,
    conversion: Callable[[object], Any],
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> Callable[..., Any] | None:
    """The conversion for one tracked argument, `int`'s downgrade for another form, or None."""
    if len(args) == 1 and not kwargs and type(args[0]) in _TRACKED:
        return conversion
    if builtin is int and args and type(args[0]) is ConcolicStr:
        return int_in_another_form
    return None


def _mapped(args: tuple[object, ...]) -> Callable[..., Any] | None:
    """`map` with `int`, `float` or `bool` first: map with pyct's conversion in its place."""
    for builtin, _ in _CONVERSIONS:
        if args and args[0] is builtin:
            return _MAPS[builtin]
    return None


def _converting(builtin: type) -> Callable[..., object]:
    """What `map` calls on each item in the builtin's place: pyct's answer, or Python's own.

    `map` calls it from C, with no router under it, so Python's own answer
    marks its raise as the target's here.
    """

    def convert(*args: object, **kwargs: object) -> object:
        conversion = picked(builtin, args, kwargs)
        return own(builtin, *args, **kwargs) if conversion is None else conversion(*args, **kwargs)

    return convert


def _mapping(builtin: type) -> Callable[..., object]:
    """`map(builtin, ...)` as Python's own map, lazy as it is, calling pyct's conversion."""
    converter = _converting(builtin)

    def mapped(_builtin: object, /, *iterables: object, **kwargs: object) -> object:
        return own(map, converter, *iterables, **kwargs)

    return mapped


_MAPS: dict[type, Callable[..., object]] = {
    builtin: _mapping(builtin) for builtin, _ in _CONVERSIONS
}


def _text(value: object) -> ConcolicStr:
    if type(value) is not ConcolicStr:
        raise TypeError(f"pyct reads a tracked str here, not {type(value).__name__}")
    return value


def _number(value: object) -> ConcolicInt | ConcolicBool:
    if type(value) is not ConcolicInt and type(value) is not ConcolicBool:
        raise TypeError(f"pyct converts a tracked int or bool here, not {type(value).__name__}")
    return value


def _tested(value: object) -> ConcolicInt | ConcolicFloat | ConcolicStr:
    if type(value) is ConcolicInt or type(value) is ConcolicFloat or type(value) is ConcolicStr:
        return value
    raise TypeError(f"pyct tests a tracked number or str here, not {type(value).__name__}")
