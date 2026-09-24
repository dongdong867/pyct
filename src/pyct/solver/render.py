"""A path of forks written out as the SMT-LIB program cvc5 reads."""

import ast
from collections.abc import Callable, Mapping

from pyct.core.branch import Branch, Expression
from pyct.solver.strings import encode

# the sort of every type pyct binds. Nothing else reaches a solver yet.
SORTS: Mapping[type, str] = {int: "Int", str: "String"}

# what opens a string literal in an expression: repr writes one in either quote, and a
# parameter name holds neither
_QUOTES = ("'", '"')

# Python's spelling of an operator, and SMT-LIB's. This is the one place the two meet, so
# a head that is missing raises here and names the gap, rather than handing cvc5 a program
# it cannot parse, which comes back as `solver failed`.
OPERATORS: Mapping[str, str] = {
    "<": "<",
    "<=": "<=",
    ">": ">",
    ">=": ">=",
    "==": "=",
    "!=": "distinct",
    "+": "+",
    "-": "-",
    "*": "*",
    "abs": "abs",
    "**": "^",
}


def _euclidean_agrees(dividend: str, divisor: str) -> str:
    """When SMT-LIB's division is already Python's: a positive divisor, or nothing left over."""
    return f"(or (> {divisor} 0) (= (mod {dividend} {divisor}) 0))"


# SMT-LIB's `div` and `mod` are Euclidean: the remainder is never negative. Python floors
# toward minus infinity and its `%` takes the divisor's sign. The two agree when the divisor
# is positive or the remainder is zero; otherwise Python's quotient is one lower and its
# remainder is shifted by the divisor. Decision division-floor-correction-in-render.
def _floor_division(dividend: str, divisor: str) -> str:
    quotient = f"(div {dividend} {divisor})"
    return f"(ite {_euclidean_agrees(dividend, divisor)} {quotient} (- {quotient} 1))"


def _modulo(dividend: str, divisor: str) -> str:
    remainder = f"(mod {dividend} {divisor})"
    return f"(ite {_euclidean_agrees(dividend, divisor)} {remainder} (+ {remainder} {divisor}))"


# an operation SMT-LIB has no operator for, written out as the form that means it. The
# operands arrive rendered, so a form only joins text.
FORMS: Mapping[str, Callable[[str, str], str]] = {"//": _floor_division, "%": _modulo}


def render(prefix: tuple[Branch, ...], leaves: Mapping[str, type]) -> str:
    """The whole little program: what to declare, what to assert, what to ask.

    Only the leaves the prefix mentions are declared, so the answer names
    nothing the path did not depend on.
    """
    mentioned = _mentioned(prefix, leaves)
    lines = ["(set-logic ALL)"]
    lines += [f"(declare-const {name} {_sort(name, leaves[name])})" for name in mentioned]
    lines += [_assertion(fork) for fork in prefix]
    lines.append("(check-sat)")
    lines += [f"(get-value ({name}))" for name in mentioned]
    return "\n".join(lines) + "\n"


def _mentioned(prefix: tuple[Branch, ...], leaves: Mapping[str, type]) -> list[str]:
    """The leaves the prefix names, in the order the seed bound them."""
    named: set[str] = set()
    for fork in prefix:
        named |= _names(fork.expression)
    unknown = sorted(named - set(leaves))
    if unknown:
        raise ValueError(f"the path names what the seed does not bind: {', '.join(unknown)}")
    return [name for name in leaves if name in named]


def _names(expression: Expression) -> set[str]:
    """Every parameter name in a condition. A list leads with its operator, not a leaf."""
    if isinstance(expression, str):
        return set() if _is_literal(expression) else {expression}
    if isinstance(expression, list):
        return {name for part in expression[1:] for name in _names(part)}
    return set()


def _sort(name: str, kind: type) -> str:
    sort = SORTS.get(kind)
    if sort is None:
        raise ValueError(f"pyct cannot declare {name}: nothing solves a {kind.__name__} yet")
    return sort


def _assertion(fork: Branch) -> str:
    """The condition as the run met it: the side it took decides the negation."""
    condition = _expression(fork.expression)
    return f"(assert {condition})" if fork.taken else f"(assert (not {condition}))"


def _expression(expression: Expression) -> str:
    """One condition, operator first. A negative number is a subtraction from nothing."""
    if isinstance(expression, bool):
        return "true" if expression else "false"
    if isinstance(expression, int):
        return f"(- {-expression})" if expression < 0 else str(expression)
    if isinstance(expression, str):
        return _string(expression) if _is_literal(expression) else expression
    head, *operands = expression
    rendered = [_expression(part) for part in operands]
    form = FORMS.get(head) if isinstance(head, str) else None
    if form is not None and len(rendered) == 2:
        return form(rendered[0], rendered[1])
    return "({} {})".format(_operator(head), " ".join(rendered))


def _is_literal(leaf: str) -> bool:
    """Whether a str leaf is a string literal, which opens with a quote, or a parameter name."""
    return leaf.startswith(_QUOTES)


def _string(literal: str) -> str:
    """A string literal, written as repr writes it, rewritten as SMT-LIB writes it."""
    value = ast.literal_eval(literal)
    if not isinstance(value, str):
        raise ValueError(f"pyct cannot render {literal}: it is not a string literal")
    return encode(value)


def _operator(head: Expression) -> str:
    """How SMT-LIB spells the operator a condition leads with."""
    operator = OPERATORS.get(head) if isinstance(head, str) else None
    if operator is None:
        raise ValueError(f"pyct cannot render {head}: nothing encodes it yet")
    return operator
