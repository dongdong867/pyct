"""An array value as cvc5 writes it in a model, read back as the values it holds.

cvc5 writes an array as a constant array and the stores over it, outermost last:
``(store (store ((as const (Array Int Int)) 0) 0 1) 3 101)`` holds 1 at 0, 101 at 3 and 0
everywhere else. An item may itself be an array, for a list of lists, and a number may be
negative, ``(- 1)``. A chain of stores is as long as the positions a model names, thousands for
a long list, so it is read with a stack of its own, never by recursion.
"""

from __future__ import annotations

import re

from pyct.binding.shapes import ArrayValue
from pyct.solver.strings import decode

# one token of a model line: a parenthesis, a string literal with its doubled quotes, or an atom
_TOKEN = re.compile(r'\(|\)|"(?:[^"]|"")*"|[^\s()"]+')

# a parsed s-expression: an atom or a string literal as its text, or a list of them
type _Sexp = str | list[_Sexp]


class ArrayModelError(ValueError):
    """An array value pyct cannot read."""


def value_line(line: str) -> tuple[str, object]:
    """The name and value of a model line ``((name value))`` whose value is an array or a number.

    A name in bars is read without them, as SMT-LIB reads it.
    """
    parsed = _parsed(line)
    match parsed:
        case [[str() as name, value]]:
            return name.strip("|"), _value(value)
    raise ArrayModelError(f"not a value line: {line}")


def _parsed(text: str) -> _Sexp:
    """The one s-expression a line holds, parsed on a stack of its own."""
    stack: list[list[_Sexp]] = [[]]
    for token in _TOKEN.findall(text):
        if token == "(":
            stack.append([])
        elif token == ")":
            if len(stack) < 2:
                raise ArrayModelError(f"unbalanced: {text}")
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(token)
    if len(stack) != 1 or len(stack[0]) != 1:
        raise ArrayModelError(f"not one expression: {text}")
    return stack[0][0]


def _value(sexp: _Sexp) -> object:
    """A number, a string, or an array."""
    if isinstance(sexp, str):
        return _atom(sexp)
    match sexp:
        case ["-", str() as digits]:
            return -int(digits)
        case [["as", "const", _], default]:
            return ArrayValue(_value(default))
        case ["store", *_]:
            return _stored(sexp)
    raise ArrayModelError(f"not a value pyct reads: {sexp}")


def _atom(text: str) -> object:
    if text.startswith('"'):
        return decode(text)
    if text.isdigit():
        return int(text)
    raise ArrayModelError(f"not a value pyct reads: {text}")


def _stored(sexp: list[_Sexp]) -> ArrayValue:
    """A chain of stores over a constant array, read from the outermost store in: an outer
    store at a position hides any inner one there."""
    stored: dict[int, object] = {}
    node: _Sexp = sexp
    while isinstance(node, list) and len(node) == 4 and node[0] == "store":
        position = _value(node[2])
        if not isinstance(position, int):
            raise ArrayModelError(f"not a position: {node[2]}")
        stored.setdefault(position, _value(node[3]))
        node = node[1]
    base = _value(node)
    if not isinstance(base, ArrayValue):
        raise ArrayModelError(f"not an array: {node}")
    return ArrayValue(base.default, {**base.stored, **stored})
