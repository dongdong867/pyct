"""Every head render writes: its result's type, and how SMT-LIB spells it on each type.

Python's spelling and SMT-LIB's meet in these tables. `render` reads them to
type each part of a condition and write it: an operator by `OPERATORS`, an
operation SMT-LIB has no operator for by the form in `FORMS`, a piece by
`POSITIONED`, and an order on strings by `STRING_ORDERS`.
"""

from collections.abc import Callable, Mapping

from pyct.solver.ints import floor_division, modulo
from pyct.solver.strings import (
    character,
    contains,
    ends_with,
    first_index,
    last_index,
    occurrences,
    replaced,
    sliced,
    starts_with,
    without_prefix,
    without_suffix,
)

# the sort of every type pyct binds. Nothing else reaches a solver yet.
SORTS: Mapping[type, str] = {int: "Int", str: "String"}

# the type of the value each head builds, as Python has it, so a head above it knows what its
# operands are: `+` joins two strs and adds two ints. None is a head whose value has its
# operands' type. Every head render writes has an entry, and a new type adds its own
RESULTS: Mapping[str, type | None] = {
    "<": bool,
    "<=": bool,
    ">": bool,
    ">=": bool,
    "==": bool,
    "!=": bool,
    "in": bool,
    "startswith": bool,
    "endswith": bool,
    # core writes `&`, `|` and `^` between two bools only; on ints they stay downgrades
    "&": bool,
    "|": bool,
    "^": bool,
    "+": None,
    "-": None,
    "*": None,
    "**": None,
    "abs": None,
    "//": None,
    "%": None,
    "find": int,
    "rfind": int,
    "index": int,
    "rindex": int,
    "count": int,
    "len": int,
    "[]": str,
    "[:]": str,
    "replace": str,
    "removeprefix": str,
    "removesuffix": str,
}

# Python's spelling of an operator on operands of one type, and SMT-LIB's. This is the one
# place the two meet, so a head that is missing raises here and names the gap, rather than
# handing cvc5 a program it cannot parse, which comes back as `solver failed`.
OPERATORS: Mapping[tuple[str, type], str] = {
    ("<", int): "<",
    ("<=", int): "<=",
    (">", int): ">",
    (">=", int): ">=",
    ("==", int): "=",
    ("!=", int): "distinct",
    ("+", int): "+",
    ("-", int): "-",
    ("*", int): "*",
    ("abs", int): "abs",
    ("**", int): "^",
    ("==", str): "=",
    ("!=", str): "distinct",
    ("+", str): "str.++",
    ("len", str): "str.len",
    ("==", bool): "=",
    ("!=", bool): "distinct",
    ("&", bool): "and",
    ("|", bool): "or",
    ("^", bool): "xor",
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


# an operation SMT-LIB has no operator for, or spells in another order, written out as the form
# that means it. The operands arrive rendered, as many as the expression holds and in its
# order, so a form only joins text.
FORMS: Mapping[str, Callable[..., str]] = {
    "//": floor_division,
    "%": modulo,
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
    "replace": replaced,
    "removeprefix": without_prefix,
    "removesuffix": without_suffix,
}

# a piece taken at positions: the string arrives rendered, and each position as the plain int
# it is, or None for a slice's missing bound, so the form sees its sign
POSITIONED: Mapping[str, Callable[..., str]] = {"[]": character, "[:]": sliced}
