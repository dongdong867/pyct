"""Every head render writes: its result's type, and how SMT-LIB spells it on each type.

Python's spelling and SMT-LIB's meet in these tables. `render` reads them to
type each part of a condition and write it: an operator by `OPERATORS`, an
operation SMT-LIB has no operator for by the form in `FORMS`, a piece by
`POSITIONED`, and an order on strings by `STRING_ORDERS`.
"""

from collections.abc import Callable, Mapping

from pyct.solver import floats
from pyct.solver.cases import CASES, PADDINGS
from pyct.solver.checks import CHECKS
from pyct.solver.ints import floor_division, modulo
from pyct.solver.recased import TO_DECLARE
from pyct.solver.splits import SPLITS
from pyct.solver.strings import (
    character,
    contains,
    ends_with,
    first_index,
    last_index,
    not_contains,
    occurrences,
    replaced,
    sliced,
    starts_with,
    without_prefix,
    without_suffix,
)

# the sort of every type pyct binds. Nothing else reaches a solver yet. Float64 is SMT-LIB's
# name for the IEEE double, `(_ FloatingPoint 11 53)`
SORTS: Mapping[type, str] = {int: "Int", str: "String", float: "Float64"}

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
    "not in": bool,
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
    # `/` answers a float in Python whatever numbers it divides
    "/": float,
    "is_integer": bool,
    "isfinite": bool,
    # a rounding answers an int, from a float
    **dict.fromkeys(("floor", "ceil", "trunc", "round"), int),
    "find": int,
    "rfind": int,
    "index": int,
    "rindex": int,
    "count": int,
    "len": int,
    # a character's code and a code's character, where pyct binds `ord` and `chr`
    "ord": int,
    "chr": str,
    "[]": str,
    "[:]": str,
    "replace": str,
    "removeprefix": str,
    "removesuffix": str,
    **dict.fromkeys(CHECKS, bool),
    **dict.fromkeys([*CASES, *PADDINGS, *TO_DECLARE], str),
    # a split builds a list, which SMT-LIB has no sort for here: its term is the string it splits,
    # and only its pieces are read, each through `[]`
    **dict.fromkeys(SPLITS, list),
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
    # cvc5 holds characters up to U+2FFFF: `str.from_code` of a code past it is the empty string,
    # where Python's `chr` is one character, so a path through one may leave the plan
    ("ord", str): "str.to_code",
    ("chr", int): "str.from_code",
    ("==", bool): "=",
    ("!=", bool): "distinct",
    ("&", bool): "and",
    ("|", bool): "or",
    ("^", bool): "xor",
    ("<", float): "fp.lt",
    ("<=", float): "fp.leq",
    (">", float): "fp.gt",
    (">=", float): "fp.geq",
    # IEEE equality, as Python's: SMT-LIB's `=` calls NaN equal to itself and tells -0.0
    # from 0.0 (see `solver/floats.py`)
    ("==", float): "fp.eq",
    ("+", float): "fp.add RNE",
    ("*", float): "fp.mul RNE",
    ("/", float): "fp.div RNE",
    ("abs", float): "fp.abs",
}

# the type a head works on whatever its operands are: Python's `/` divides two ints as floats
WORKS_ON: Mapping[str, type] = {"/": float}

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
# that means it. Keyed by head and the type the operation works on, as `OPERATORS` is, so `//`
# on ints and `//` on floats can each have their own. The operands arrive rendered, as many as
# the expression holds and in its order, so a form only joins text.
FORMS: Mapping[tuple[str, type], Callable[..., str]] = {
    ("//", int): floor_division,
    ("%", int): modulo,
    ("in", str): contains,
    ("not in", str): not_contains,
    ("startswith", str): starts_with,
    ("endswith", str): ends_with,
    ("find", str): first_index,
    ("rfind", str): last_index,
    ("count", str): occurrences,
    # index and rindex answer only past their `in` fork, where sub is in s and each is the
    # find it mirrors
    ("index", str): first_index,
    ("rindex", str): last_index,
    ("replace", str): replaced,
    ("removeprefix", str): without_prefix,
    ("removesuffix", str): without_suffix,
    ("!=", float): floats.unequal,
    ("-", float): floats.minus,
    ("is_integer", float): floats.whole,
    ("isfinite", float): floats.finite,
    ("%", float): floats.modulo,
    ("floor", float): floats.floor,
    ("ceil", float): floats.ceil,
    ("trunc", float): floats.trunc,
    ("round", float): floats.rounded,
    **{(head, str): form for head, form in CASES.items()},
}

# a form exact only inside a bound, which answers its term and the bound, keyed as `FORMS` is.
# Render holds the bound on the path (see `Program.bounded` in `solver/render.py`)
BOUNDED: Mapping[tuple[str, type], Callable[..., tuple[str, str]]] = {
    ("//", float): floats.floor_division,
}

# a string taken at positions or padded: the string arrives rendered, and each other operand as
# the plain value it is, an int, None for a slice's missing bound, or a literal's str, so the
# form sees a position's sign and cuts a padding to its width
POSITIONED: Mapping[str, Callable[..., str]] = {"[]": character, "[:]": sliced, **PADDINGS}
