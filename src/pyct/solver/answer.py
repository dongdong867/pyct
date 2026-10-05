"""What a solver can say back, and how to read the values it gives."""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from pyct.solver import floats, strings
from pyct.solver.arrays import ArrayModelError, value_line

# one value of a model, as cvc5 writes it: ((x 5)), ((x (- 6))), ((s "a""b\u{a}")) or
# ((f (fp #b0 #b10000000000 #b0100...))) or ((b true)). A name may come in bars, ((|x| 5)),
# which SMT-LIB reads as the same name. A string value holds no bare quote, only a doubled one,
# so its closing quote is the first lone one. A double's value is its three fields, which
# `floats.decode` reads
VALUE_LINE = re.compile(
    r"\(\(\|?(?P<name>[^\s()|]+)\|? "
    r'(?P<value>\(- \d+\)|-?\d+|"(?:[^"]|"")*"|\(fp [^()]*\)|true|false)\)\)'
)
# how SMT-LIB writes each value of the Bool sort
_BOOLS = {"true": True, "false": False}


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

    # whether pyct gave the ask up before cvc5 ran, as a step guard does: it cost no solver time
    unasked: bool = field(default=False, compare=False)


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


def model_from(lines: Iterable[str]) -> dict[str, object]:
    """The values cvc5 printed, as a name and an int, a bool, a str, a float or an array each.

    A line pyct cannot read is an error rather than a skip: a model missing
    one of its leaves would quietly become the seed's value again.
    """
    return dict(_value(line) for line in lines)


def _value(line: str) -> tuple[str, object]:
    """One name and its value: a leaf's, or an array read as the values it holds (see
    ``arrays``)."""
    matched = VALUE_LINE.fullmatch(line.strip())
    if matched is None:
        try:
            return value_line(line)
        except ArrayModelError as error:
            raise _unreadable(line) from error
    try:
        return matched["name"], _read(matched["value"])
    except ValueError as error:
        raise _unreadable(line) from error


def _read(value: str) -> int | str | float:
    """A value in quotes is a string, one in three fields a double, `true` or `false` a bool,
    and any other an int."""
    if value in _BOOLS:
        return _BOOLS[value]
    if value.startswith('"'):
        return strings.decode(value)
    if value.startswith("(fp "):
        return floats.decode(value)
    return _number(value)


def _unreadable(line: str) -> SolverAnswerError:
    """The error for a value line pyct cannot read, which names the line."""
    return SolverAnswerError(f"cvc5 answered with a value line pyct cannot read: {line}")


def _number(text: str) -> int:
    """The integer of a value. A negative one is written as a subtraction from nothing."""
    if text.startswith("("):
        return -int(text[len("(- ") : -1])
    return int(text)
