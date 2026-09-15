"""A path of forks written out as the SMT-LIB program cvc5 reads."""

from collections.abc import Mapping

from pyct.core.branch import Branch, Expression

# the sort of every type pyct binds. Nothing else reaches a solver yet.
SORTS: Mapping[type, str] = {int: "Int"}

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
        return {expression}
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
        return expression
    head, *operands = expression
    return "({} {})".format(_operator(head), " ".join(_expression(part) for part in operands))


def _operator(head: Expression) -> str:
    """How SMT-LIB spells the operator a condition leads with."""
    operator = OPERATORS.get(head) if isinstance(head, str) else None
    if operator is None:
        raise ValueError(f"pyct cannot render {head}: nothing encodes it yet")
    return operator
