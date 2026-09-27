"""A path of forks written out as the SMT-LIB program cvc5 reads."""

import ast
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from pyct.binding.bind import access_name
from pyct.core.branch import Branch, Expression
from pyct.solver.strings import (
    above,
    below,
    contains,
    encode,
    ends_with,
    first_index,
    last_index,
    occurrences,
    starts_with,
)

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

# Python's order on two strings, read as a less-than: whether it takes equal strings, and
# whether its operands swap. `a > b` is written `b < a`, the same term the target would have
# met had it written that
STRING_ORDERS: Mapping[str, tuple[bool, bool]] = {
    "<": (False, False),
    "<=": (True, False),
    ">": (False, True),
    ">=": (True, True),
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


# an operation SMT-LIB has no operator for, or spells in another order, written out as the form
# that means it. The operands arrive rendered, in the expression's order, so a form only joins
# text.
FORMS: Mapping[str, Callable[[str, str], str]] = {
    "//": _floor_division,
    "%": _modulo,
    "in": contains,
    "startswith": starts_with,
    "endswith": ends_with,
    "find": first_index,
    "rfind": last_index,
    "count": occurrences,
    # index and rindex answer only past their `in` fork, where sub is in s and each is the
    # find it mirrors
    "index": first_index,
    "rindex": last_index,
}


@dataclass(frozen=True)
class _Leaves:
    """The seed's leaves by name, with their types and the constant each mentioned one gets."""

    kinds: Mapping[str, type]
    constants: Mapping[str, str]

    def named(self, part: Expression) -> str | None:
        """The name of the leaf a part of a condition is, or None for a literal or an operation.

        A parameter is its bare name. A value inside one is its access, which
        reads as an operation does: only an access to one of the seed's own
        leaves is a value, and any other is an operation on a tracked value.
        Which steps an access takes is binding's to say (``access_name``).
        """
        if isinstance(part, str):
            return None if _is_literal(part) else part
        name = access_name(part)
        return name if name in self.kinds else None

    def kind(self, part: Expression) -> type | None:
        """The type of the leaf a part is, or None for anything else."""
        name = self.named(part)
        return None if name is None else self.kinds.get(name)


@dataclass(frozen=True)
class Program:
    """The SMT-LIB program for one path, and the leaf each constant it declares stands for.

    ``leaves`` is keyed by each constant's symbol without its bars, which is
    how a model names it back.
    """

    text: str
    leaves: Mapping[str, str]

    def read(self, model: Mapping[str, object]) -> dict[str, object]:
        """A model cvc5 wrote by constant, named by the leaves the constants were declared for."""
        return {self.leaves[constant]: value for constant, value in model.items()}


def program(prefix: tuple[Branch, ...], leaves: Mapping[str, type]) -> Program:
    """The program for a path, with the table that reads its answer back.

    Only the leaves the prefix mentions are declared, so the answer names
    nothing the path did not depend on. ``leaves`` names each leaf as
    ``pyct.binding`` does, and ``_symbol`` names its constant.
    """
    symbols = _symbols(prefix, leaves)
    constants = {name: f"|{symbol}|" for name, symbol in symbols.items()}
    known = _Leaves(kinds=leaves, constants=constants)
    declared = [(constant, _sort(name, leaves[name])) for name, constant in constants.items()]
    lines = ["(set-logic ALL)"]
    lines += [f"(declare-const {constant} {sort})" for constant, sort in declared]
    lines += [_assertion(fork, known) for fork in prefix]
    lines.append("(check-sat)")
    lines += [f"(get-value ({constant}))" for constant, _ in declared]
    text = "\n".join(lines) + "\n"
    return Program(text=text, leaves={symbol: name for name, symbol in symbols.items()})


def _symbols(prefix: tuple[Branch, ...], leaves: Mapping[str, type]) -> dict[str, str]:
    """The symbol of each leaf the prefix names, in the order the seed bound them."""
    known = _Leaves(kinds=leaves, constants={})
    named: set[str] = set()
    for fork in prefix:
        named |= _names(fork.expression, known)
    unknown = sorted(named - set(leaves))
    if unknown:
        raise ValueError(f"the path names what the seed does not bind: {', '.join(unknown)}")
    return {name: _symbol(name, index) for index, name in enumerate(leaves) if name in named}


def _symbol(name: str, index: int) -> str:
    """A leaf's symbol, written inside bars: ``arg.<name>`` for a parameter, else ``leaf.<n>``.

    The prefix keeps every symbol apart from the solver's own words, which
    a parameter may be named as, ``div`` say: cvc5 refuses to declare one,
    bars or not. A parameter's name is an identifier; each character past
    ASCII is written as its UTF-8 bytes, ``%C3%A9`` for ``é``, so the program
    stays ASCII. Any other leaf is ``leaf.<n>``, n its position among the
    seed's leaves: a value inside an argument is named by its access, which
    holds brackets, quotes, and any character a key holds, ``|`` and the
    backslash among them, which not even a quoted symbol can.
    """
    if not name.isidentifier():
        return f"leaf.{index}"
    written = "".join(
        character if character.isascii() else "".join(f"%{byte:02X}" for byte in character.encode())
        for character in name
    )
    return f"arg.{written}"


def _names(expression: Expression, leaves: _Leaves) -> set[str]:
    """Every leaf a condition names. A list leads with its operator, not a leaf."""
    name = leaves.named(expression)
    if name is not None:
        return {name}
    if isinstance(expression, list):
        return {name for part in expression[1:] for name in _names(part, leaves)}
    return set()


def _sort(name: str, kind: type) -> str:
    sort = SORTS.get(kind)
    if sort is None:
        raise ValueError(f"pyct cannot declare {name}: nothing solves a {kind.__name__} yet")
    return sort


def _assertion(fork: Branch, leaves: _Leaves) -> str:
    """The condition as the run met it: the side it took decides the negation."""
    condition = _expression(fork.expression, leaves)
    return f"(assert {condition})" if fork.taken else f"(assert (not {condition}))"


def _expression(expression: Expression, leaves: _Leaves) -> str:
    """One condition, operator first. A negative number is a subtraction from nothing."""
    if isinstance(expression, bool):
        return "true" if expression else "false"
    if isinstance(expression, int):
        return f"(- {-expression})" if expression < 0 else str(expression)
    name = leaves.named(expression)
    if name is not None:
        return leaves.constants[name]
    if isinstance(expression, str):
        return encode(_value(expression))
    head, *operands = expression
    rendered = [_expression(part, leaves) for part in operands]
    form = FORMS.get(head) if isinstance(head, str) else None
    if form is not None and len(rendered) == 2:
        return form(rendered[0], rendered[1])
    if isinstance(head, str) and head in STRING_ORDERS and _on_strings(operands, leaves):
        return _string_order(head, operands, rendered)
    return "({} {})".format(_operator(head), " ".join(rendered))


def _on_strings(operands: list[Expression], leaves: _Leaves) -> bool:
    """Whether a compare's operands are strings: a string literal, or a leaf bound to a str.

    Both operands of a compare are of one sort, so one string between them decides it.
    """
    return any(_literal(part) is not None or leaves.kind(part) is str for part in operands)


def _string_order(head: str, operands: list[Expression], rendered: list[str]) -> str:
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


def _is_literal(leaf: str) -> bool:
    """Whether a str leaf is a string literal, which opens with a quote, or a parameter name."""
    return leaf.startswith(_QUOTES)


def _literal(part: Expression) -> str | None:
    """The value of an operand that is a string literal, or None for any other operand."""
    return _value(part) if isinstance(part, str) and _is_literal(part) else None


def _value(literal: str) -> str:
    """The str a string literal, written as repr writes it, holds."""
    value = ast.literal_eval(literal)
    if not isinstance(value, str):
        raise ValueError(f"pyct cannot render {literal}: it is not a string literal")
    return value


def _operator(head: Expression) -> str:
    """How SMT-LIB spells the operator a condition leads with."""
    operator = OPERATORS.get(head) if isinstance(head, str) else None
    if operator is None:
        raise ValueError(f"pyct cannot render {head}: nothing encodes it yet")
    return operator
