"""What Python makes of a list's form: the expression evaluated over the arguments.

A tracked list's form is the Python expression that builds it from the arguments, so the tests
hold it against Python by evaluating it here: a list display, `+`, `*`, an index, a slice with
or without a step, `len`, unary `-`, a parameter's name and a literal. A fork on a dict is held
the same way, so `in`, binary `-` and the compares are evaluated too.
"""

import ast
import operator
from collections.abc import Callable, Mapping
from typing import Any

from pyct.core.branch import Expression


def evaluate(expression: Expression, args: Mapping[str, object]) -> object:
    """The value Python gives the expression, the arguments standing for their names.

    Evaluated on a stack of its own, since a list the target changed thousands of times is
    that many levels deep.
    """
    done: dict[int, object] = {}
    stack: list[tuple[Expression, bool]] = [(expression, False)]
    while stack:
        part, ready = stack.pop()
        if not isinstance(part, list) or id(part) in done:
            continue
        if not ready:
            stack.append((part, True))
            stack.extend((operand, False) for operand in part[1:])
            continue
        head, *operands = part
        values = [_value(operand, args, done) for operand in operands]
        done[id(part)] = _apply(str(head), values)
    return _value(expression, args, done)


def _value(part: Expression, args: Mapping[str, object], done: dict[int, object]) -> object:
    if isinstance(part, list):
        return done[id(part)]
    if isinstance(part, str):
        return ast.literal_eval(part) if part.startswith(("'", '"')) else args[part]
    return part


def _apply(head: str, values: list[Any]) -> object:
    if head == "[,]":
        return list(values)
    if head == "[]":
        container, key = values
        return container[key]
    if head == "[:]":
        container, *bounds = values
        return container[slice(*bounds)]
    if head == "len":
        return len(values[0])
    if head == "-" and len(values) == 1:
        return -values[0]
    left, right = values
    if head == "in":
        return left in right
    if head in _BINARY:
        return _BINARY[head](left, right)
    raise ValueError(f"no Python meaning for {head}")


# the operators a fork on a list or a dict is written with, by their head
_BINARY: Mapping[str, Callable[[Any, Any], object]] = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}
