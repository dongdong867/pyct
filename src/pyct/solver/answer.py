"""What a solver can say back, and how to read the values it gives."""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# one value of a model, as cvc5 writes it: ((x 5)) or ((x (- 6)))
VALUE_LINE = re.compile(r"\(\((?P<name>[^\s()]+) (?P<value>\(- \d+\)|-?\d+)\)\)")


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


def model_from(lines: Iterable[str]) -> dict[str, int]:
    """The values cvc5 printed, as a name and a number each.

    A line pyct cannot read is an error rather than a skip: a model missing
    one of its leaves would quietly become the seed's value again.
    """
    return dict(_value(line) for line in lines)


def _value(line: str) -> tuple[str, int]:
    matched = VALUE_LINE.fullmatch(line.strip())
    if matched is None:
        raise ValueError(f"cvc5 answered with a value line pyct cannot read: {line}")
    return matched["name"], _number(matched["value"])


def _number(text: str) -> int:
    """The integer of a value. A negative one is written as a subtraction from nothing."""
    if text.startswith("("):
        return -int(text[len("(- ") : -1])
    return int(text)
