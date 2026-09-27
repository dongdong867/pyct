"""How render reads a literal out of a condition, and writes one: a string literal's str, a plain
operand, and the term of a number, a truth value or a string literal."""

import ast

from pyct.core.branch import Expression
from pyct.solver import floats
from pyct.solver.strings import encode

# what opens a string literal in an expression: repr writes one in either quote, and a
# parameter name holds neither
_QUOTES = ("'", '"')


def plain_operand(part: Expression) -> int | str | None:
    """An operand a form takes as it is: an int or a bool, None for a slice's missing bound, or
    a string literal's str. A name is not one."""
    if part is None or isinstance(part, int):
        return part
    if isinstance(part, str) and is_literal(part):
        return value(part)
    raise ValueError(
        f"pyct cannot render {part} as a position, a separator or a fill: core writes a plain "
        "value there"
    )


def is_literal(leaf: str) -> bool:
    """Whether a str leaf is a string literal, which opens with a quote, or a parameter name."""
    return leaf.startswith(_QUOTES)


def literal_of(part: Expression) -> str | None:
    """The value of an operand that is a string literal, or None for any other operand."""
    return value(part) if isinstance(part, str) and is_literal(part) else None


def value(literal: str) -> str:
    """The str a string literal, written as repr writes it, holds."""
    held = ast.literal_eval(literal)
    if not isinstance(held, str):
        raise ValueError(f"pyct cannot render {literal}: it is not a string literal")
    return held


def leaf_term(leaf: str | int | float | bool | None) -> str:
    """A number, a truth value or a string literal.

    A negative int is a subtraction, and a float is its bit pattern, sign and all.
    """
    if leaf is None:
        raise ValueError("pyct cannot render a missing bound outside a slice")
    if isinstance(leaf, bool):
        return "true" if leaf else "false"
    if isinstance(leaf, int):
        return f"(- {-leaf})" if leaf < 0 else str(leaf)
    if isinstance(leaf, float):
        return floats.literal(leaf)
    return encode(value(leaf))
