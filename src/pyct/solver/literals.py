"""The plain operands of a condition as the program writes them: a literal, a number, a
position or a fill a form takes as it is, and an order on strings."""

import ast

from pyct.core.branch import Expression
from pyct.solver import floats
from pyct.solver.heads import STRING_ORDERS
from pyct.solver.strings import above, below, encode

# what opens a string literal in an expression: repr writes one in either quote, and a
# parameter name holds neither
_QUOTES = ("'", '"')


def leaf(leaf: str | int | float | bool | None) -> str:
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
    return encode(_value(leaf))


def plain(part: Expression) -> int | str | None:
    """An operand a form takes as it is: an int or a bool, None for a slice's missing bound, or
    a string literal's str. A name is not one."""
    if part is None or isinstance(part, int):
        return part
    if isinstance(part, str) and is_literal(part):
        return _value(part)
    raise ValueError(
        f"pyct cannot render {part} as a position, a separator or a fill: core writes a plain "
        "value there"
    )


def string_order(head: str, operands: list[Expression], rendered: list[str]) -> str:
    """An order on two strings as a less-than: against a literal, written letter by letter.

    Between two tracked strings it is cvc5's own `str.<` or `str.<=`. cvc5's
    order against a literal can run to any time limit where the letters are
    answered at once: string-order-against-a-literal-letter-by-letter.
    """
    or_equal, swapped = STRING_ORDERS[head]
    pairs = list(zip(operands, rendered, strict=True))
    (low, low_term), (high, high_term) = reversed(pairs) if swapped else pairs
    if (literal := _literal(high)) is not None:
        return below(low_term, literal, or_equal=or_equal)
    if (literal := _literal(low)) is not None:
        return above(high_term, literal, or_equal=or_equal)
    return f"({'str.<=' if or_equal else 'str.<'} {low_term} {high_term})"


def is_literal(leaf: str) -> bool:
    """Whether a str leaf is a string literal, which opens with a quote, or a parameter name."""
    return leaf.startswith(_QUOTES)


def _literal(part: Expression) -> str | None:
    """The value of an operand that is a string literal, or None for any other operand."""
    return _value(part) if isinstance(part, str) and is_literal(part) else None


def _value(literal: str) -> str:
    """The str a string literal, written as repr writes it, holds."""
    value = ast.literal_eval(literal)
    if not isinstance(value, str):
        raise ValueError(f"pyct cannot render {literal}: it is not a string literal")
    return value
