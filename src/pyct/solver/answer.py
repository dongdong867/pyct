"""What a solver can say back, and how to read the values it gives."""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from pyct.solver.strings import decode

# one value of a model, as cvc5 writes it: ((x 5)), ((x (- 6))) or ((s "a""b\u{a}")). A string
# value holds no bare quote, only a doubled one, so its closing quote is the first lone one
VALUE_LINE = re.compile(r'\(\((?P<name>[^\s()]+) (?P<value>\(- \d+\)|-?\d+|"(?:[^"]|"")*")\)\)')


@dataclass(frozen=True)
class Sat:
    """The prefix is reachable, and this is an input that reaches it."""

    model: Mapping[str, object]


@dataclass(frozen=True)
class Unsat:
    """No input takes that path: the prefix contradicts itself."""


@dataclass(frozen=True)
class Unknown:
    """The solver gave up on the prefix without deciding it."""


@dataclass(frozen=True)
class Timeout:
    """The solver ran out of the time it was given."""


@dataclass(frozen=True)
class Error:
    """The solver failed to answer at all. ``detail`` is what it said."""

    detail: str


# every answer a solve can end with
type Answer = Sat | Unsat | Unknown | Timeout | Error


class SolverAnswerError(Exception):
    """cvc5 answered, but with a line pyct cannot read."""


def model_from(lines: Iterable[str]) -> dict[str, int | str]:
    """The values cvc5 printed, as a name and a number or a str each.

    A line pyct cannot read is an error rather than a skip: a model missing
    one of its leaves would quietly become the seed's value again.
    """
    return dict(_value(line) for line in lines)


def _value(line: str) -> tuple[str, int | str]:
    """One leaf's name and value. A value in quotes is a string, any other a number."""
    matched = VALUE_LINE.fullmatch(line.strip())
    if matched is None:
        raise _unreadable(line)
    value = matched["value"]
    if not value.startswith('"'):
        return matched["name"], _number(value)
    try:
        return matched["name"], decode(value)
    except ValueError as error:
        raise _unreadable(line) from error


def _unreadable(line: str) -> SolverAnswerError:
    return SolverAnswerError(f"cvc5 answered with a value line pyct cannot read: {line}")


def _number(text: str) -> int:
    """The integer of a value. A negative one is written as a subtraction from nothing."""
    if text.startswith("("):
        return -int(text[len("(- ") : -1])
    return int(text)
