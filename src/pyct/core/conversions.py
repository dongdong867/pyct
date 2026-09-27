"""What `int(x)`, `float(x)` and `bool(x)` answer on a tracked value, where the code writes them.

Python's `int` and `float` copy whatever `__int__` or `__float__` hands back
into a plain number, read a str's text without calling any of its methods,
and `bool` tests its argument for truth on the spot, so a tracked value would
lose its condition in each. pyct substitutes a call written with one of these
names (`pyct.intercept`), and when the name holds Python's own and its one
argument is tracked, `pyct.core.bound` routes it to one of these:

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
encode, is Python's own answer and a downgrade named `int`.
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


def itself(value: object) -> object:
    """A conversion to the type the value already is: the value, and no node."""
    return value


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


def int_of_text(value: ConcolicStr) -> Any:
    """`int(s)` on a tracked str."""
    return _read(value, int, "isint")


def float_of_text(value: ConcolicStr) -> Any:
    """`float(s)` on a tracked str."""
    return _read(value, float, "isfloat")


def int_of_bool(value: ConcolicBool) -> Any:
    """`int(b)` on a tracked bool: 1 or 0, carrying `["int", b]`."""
    return numbers.tracked(int.__index__(value), ["int", value.expression], value.sink)


def int_of_float(value: ConcolicFloat) -> Any:
    """`int(f)` on a tracked float: cut toward zero after its finite fork."""
    return floats.truncated(value)


def float_of_int(value: ConcolicInt | ConcolicBool) -> Any:
    """`float(n)` on a tracked int or bool, rounded as Python rounds it."""
    answer = own(int.__float__, value)
    return numbers.tracked(answer, ["float", value.expression], value.sink)


def _filled(text: str) -> bool:
    """Whether a str holds any character, read without any method of a tracked one."""
    return str.__len__(text) > 0


def _truth(test: Callable[[Any], bool], false: Expression) -> Callable[[Any], Any]:
    """`bool(x)` on a tracked value `if x:` tests against ``false``: its condition, untested."""

    def compute(value: ConcolicInt | ConcolicFloat | ConcolicStr) -> Any:
        expression = ["!=", value.expression, false]
        return ConcolicBool(own(test, value), expression=expression, sink=value.sink)

    return compute


bool_of_int = _truth(int.__bool__, 0)
bool_of_float = _truth(float.__bool__, 0.0)
bool_of_text = _truth(_filled, "''")


def int_in_another_form(value: ConcolicStr, /, *args: object, **kwargs: object) -> object:
    """`int` on a tracked str in a form pyct does not encode, `int(s, 16)` say: a downgrade.

    Python's own answer, and a note that the condition was lost, after the
    call, so a call that raises records nothing.
    """
    answer = own(int, value, *args, **kwargs)
    value.sink.append(Downgrade(name="int"))
    return answer
