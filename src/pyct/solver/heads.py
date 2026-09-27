"""Every head render writes: its result's type, and how SMT-LIB spells it on each type.

Python's spelling and SMT-LIB's meet in these tables. `render` reads them to
type each part of a condition and write it: an operator by `OPERATORS`, an
operation SMT-LIB has no operator for by the form in `FORMS`, a piece by
`POSITIONED`, and an order on strings by `STRING_ORDERS`.
"""

from collections.abc import Callable, Mapping

from pyct.solver import floats, numerals
from pyct.solver.cases import CASES, PADDINGS
from pyct.solver.checks import CHECKS
from pyct.solver.ints import floor_division, modulo
from pyct.solver.positions import (
    character,
    ends_with,
    first_index,
    last_index,
    occurrences,
    replaced,
    sliced,
    starts_with,
)
from pyct.solver.recased import TO_DECLARE
from pyct.solver.spans import equal, unequal, within, without
from pyct.solver.splits import SPLITS
from pyct.solver.strings import contains, not_contains, without_prefix, without_suffix

# the sort of every type pyct binds. Nothing else reaches a solver yet. Float64 is SMT-LIB's
# name for the IEEE double, `(_ FloatingPoint 11 53)`
SORTS: Mapping[type, str] = {int: "Int", str: "String", float: "Float64", bool: "Bool"}

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
    # the `math` functions pyct follows: each answers a float or a bool, from floats
    **dict.fromkeys(("sqrt", "fabs", "copysign"), float),
    **dict.fromkeys(("isfinite", "isnan", "isinf", "isclose"), bool),
    # a truth value negated, as `sqrt`'s fork is written
    "not": bool,
    # a rounding answers an int, from a float
    **dict.fromkeys(("floor", "ceil", "trunc", "round"), int),
    # `int` and `float` of a number or of the text Python reads, and whether it reads the text
    "int": int,
    "float": float,
    "isint": bool,
    "isfloat": bool,
    # the text `str` writes for an int or a bool
    "str": str,
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
    # a tuple of prefixes or suffixes, which SMT-LIB has no sort for: only a search reads it,
    # each item a string term
    "()": tuple,
    # a range's arguments, which SMT-LIB has no sort for either: a membership and an equality of
    # two ranges read them, each argument an Int term
    "range": range,
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
    ("sqrt", float): "fp.sqrt RNE",
    ("fabs", float): "fp.abs",
    ("isnan", float): "fp.isNaN",
    ("isinf", float): "fp.isInfinite",
    ("not", bool): "not",
}


def operator(head: str, kind: type | None) -> str:
    """How SMT-LIB spells the operator a condition leads with, on operands of that type."""
    spelled = OPERATORS.get((head, kind)) if kind is not None else None
    if spelled is None:
        on = "anything" if kind is None else kind.__name__
        raise ValueError(f"pyct cannot render {head} on {on}: nothing encodes it yet")
    return spelled


# the type a head works on whatever its operands are: Python's `/` divides two ints as floats,
# and a `math` function reads an int as the double Python converts it to
WORKS_ON: Mapping[str, type] = {
    "/": float,
    **dict.fromkeys(("sqrt", "fabs", "copysign", "isfinite", "isnan", "isinf", "isclose"), float),
}
# the heads that search a container: over a range they work on ints, whatever the item is, so a
# bool item reads as the int 1 or 0, as Python's range reads it
MEMBERSHIPS = frozenset({"in", "not in"})

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
# on ints and `//` on floats can each have their own. The operands arrive as many as the
# expression holds and in its order, each rendered, but for the positions `POSITIONS_FROM`
# names, which arrive as a plain int, None or an Int term, and a tuple of needles, which
# arrives as its items' terms.
FORMS: Mapping[tuple[str, type], Callable[..., str]] = {
    ("//", int): floor_division,
    ("%", int): modulo,
    ("in", str): contains,
    ("not in", str): not_contains,
    # an int in a range, its arguments arriving as their terms
    ("in", int): within,
    ("not in", int): without,
    # two ranges, each arriving as its arguments' terms
    ("==", range): equal,
    ("!=", range): unequal,
    ("startswith", str): starts_with,
    ("endswith", str): ends_with,
    ("find", str): first_index,
    ("rfind", str): last_index,
    ("count", str): occurrences,
    # index and rindex answer only past their found fork: `in` without a position, and the find
    # or rfind each mirrors from one. Past it each is that find
    ("index", str): first_index,
    ("rindex", str): last_index,
    ("replace", str): replaced,
    ("removeprefix", str): without_prefix,
    ("removesuffix", str): without_suffix,
    ("!=", float): floats.unequal,
    ("-", float): floats.minus,
    ("is_integer", float): floats.whole,
    ("isfinite", float): floats.finite,
    ("copysign", float): floats.copysign,
    ("isclose", float): floats.close,
    ("%", float): floats.modulo,
    ("floor", float): floats.floor,
    ("ceil", float): floats.ceil,
    ("trunc", float): floats.trunc,
    ("round", float): floats.rounded,
    # `int` of a bool reaches here as the int 1 or 0 it is, and adds nothing to it; `int` of a
    # float cuts it toward zero past its finite fork, and `float` of an int or a bool rounds it
    ("int", int): lambda term: term,
    ("int", float): floats.trunc,
    ("float", int): floats.from_int,
    ("int", str): numerals.int_of,
    ("isint", str): numerals.is_int,
    ("isfloat", str): numerals.is_float,
    # `str` of an int or a bool; a bool keeps its own sort here, as it does under `&`
    ("str", int): numerals.text_of_int,
    ("str", bool): numerals.text_of_bool,
    **{(head, str): form for head, form in CASES.items()},
}

# the forms of a head on one character of a string, `s[i]`, keyed by the head on str, which
# render writes in place of `FORMS`' own for such an operand
ON_A_CHARACTER: Mapping[str, Callable[[str], str]] = {
    "int": numerals.int_of_character,
    "isint": numerals.is_int_character,
}

# a form exact only inside a bound, which answers its term and the bound, keyed as `FORMS` is.
# Render holds the bound on the path (see `Program.bounded` in `solver/render.py`)
BOUNDED: Mapping[tuple[str, type], Callable[..., tuple[str, str]]] = {
    ("//", float): floats.floor_division,
    ("float", str): numerals.float_of,
}

# a string taken at positions or padded: the string arrives rendered, and each other operand as
# the plain value it is, an int, None for a slice's missing bound, or a literal's str, so the
# form sees a position's sign and cuts a padding to its width. An index and a slice also take
# a tracked position, as its Int term
POSITIONED: Mapping[str, Callable[..., str]] = {"[]": character, "[:]": sliced, **PADDINGS}

# the heads whose positions may be tracked: an index and a slice here, and each search and
# replace in `FORMS` by the operand its positions start at, past the string and what it looks
# for or replaces. Each position arrives as `POSITIONED`'s do, or as a tracked one's Int term
INDEXED = frozenset({"[]", "[:]"})
POSITIONS_FROM: Mapping[str, int] = {
    **dict.fromkeys(["find", "rfind", "index", "rindex", "count", "startswith", "endswith"], 2),
    "replace": 3,
}
