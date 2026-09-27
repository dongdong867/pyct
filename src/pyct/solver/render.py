"""A path of forks written out as the SMT-LIB program cvc5 reads."""

from collections.abc import Callable, Mapping

from pyct.binding.shapes import ListShape
from pyct.core.branch import Branch, Expression
from pyct.solver.dag import Node, distinct
from pyct.solver.declared import (
    SORTS,
    Leaves,
    Program,
    is_literal,
    sort_of,
    symbols,
    value_of,
)
from pyct.solver.joined import joined
from pyct.solver.lists import ListTerms, TrackedList, UnencodedError
from pyct.solver.strings import (
    above,
    below,
    character,
    contains,
    encode,
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
# that means it. The operands arrive rendered, as many as the expression holds and in its
# order, so a form only joins text.
FORMS: Mapping[str, Callable[..., str]] = {
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
    "replace": replaced,
    "removeprefix": without_prefix,
    "removesuffix": without_suffix,
}

# a piece taken at positions: the string arrives rendered, and each position as the plain int
# it is, or None for a slice's missing bound, so the form sees its sign
POSITIONED: Mapping[str, Callable[..., str]] = {"[]": character, "[:]": sliced}


# the sort of a part defined once, by the type of its value
_DEFINED_SORTS: Mapping[type, str] = {**SORTS, bool: "Bool"}


def program(
    prefix: tuple[Branch, ...],
    leaves: Mapping[str, type],
    lists: Mapping[str, ListShape] | None = None,
    until: float | None = None,
) -> Program:
    """The whole little program for a path, with the table that reads its answer back.

    What to declare, what to define, what to assert, what to ask. Only the
    leaves the prefix mentions are declared, so the answer names nothing the
    path did not depend on. ``leaves`` names each leaf as ``pyct.binding``
    does, and ``symbol`` names its constant; ``lists`` names each tracked list
    with its shape. Two pieces of one string side by side are first written as
    the one piece they make (see `joined`), and a part of the conditions written
    more than once is defined once before the assertions (see `_Program`).
    ``until`` is the monotonic instant writing must end by: a read of a list the
    target changed thousands of times stops there (``RenderTimeError``).
    """
    shapes = lists or {}
    seed = Leaves(kinds=leaves, constants={}, lists=shapes)
    listed = ListTerms(shapes, {}).listed(distinct(prefix, seed.holds)[0])
    prefix = joined(prefix, seed.holds, lambda part: id(part) in listed or part in shapes)
    order, holders = distinct(prefix, seed.holds)
    named = symbols(prefix, order, seed)
    constants = {name: f"|{symbol}|" for name, symbol in named.items() if name in leaves}
    # a leaf no sort declares is named before any term on it is written
    declared = [(constant, sort_of(name, leaves[name])) for name, constant in constants.items()]
    terms = _list_terms(shapes, {name: named[name] for name in named if name in shapes}, prefix)
    terms.until = until
    body = _Program(Leaves(kinds=leaves, constants=constants, lists=shapes), order, holders, terms)
    text = _text(prefix, body, declared)
    by_symbol = {symbol: name for name, symbol in named.items() if name in leaves}
    return Program(text=text, names_by_symbol=by_symbol, lists=terms if terms.declared else None)


def _list_terms(
    shapes: Mapping[str, ListShape], symbols: Mapping[str, str], prefix: tuple[Branch, ...]
) -> ListTerms:
    """The lists of the path, with how long the path's own forks say each is at least."""
    terms = ListTerms(shapes, symbols)
    terms.learn(prefix)
    return terms


def _text(prefix: tuple[Branch, ...], body: "_Program", declared: list[tuple[str, str]]) -> str:
    """The program's lines, in the order cvc5 reads them: each leaf and each list's parts
    declared before any term on them, the definitions, what the lists and the path assert, and
    what to ask for."""
    terms = body.lists
    lines = ["(set-logic ALL)"]
    lines += [f"(declare-const {constant} {sort})" for constant, sort in declared]
    lines += [f"(declare-const {name} {sort})" for name, sort in terms.declared.items()]
    lines += body.definitions
    lines += terms.assertions()
    lines += [body.assertion(fork) for fork in prefix]
    lines.append("(check-sat)")
    lines += [f"(get-value ({constant}))" for constant, _ in declared]
    lines += [f"(get-value ({name}))" for name in terms.asked()]
    return "\n".join(lines) + "\n"


class _Program:
    """A path's conditions, each part written once.

    Python holds a part it used twice as one list, so a string rebuilt from
    two pieces of itself holds the old one twice, and written out the
    condition doubles with each pass of the loop that built it. A part held
    in more than one place is defined once, as ``(define-fun e!N () Sort …)``,
    and named wherever it is read; so is a part a form reads, since a form
    may write its operands more than once. ``!`` is in no Python name, so a
    defined name never meets a parameter. The program then grows with the
    number of distinct parts, not with the conditions written out.
    """

    def __init__(
        self, leaves: Leaves, order: list[Node], holders: dict[int, int], lists: ListTerms
    ) -> None:
        self.leaves = leaves
        self.types: dict[int, type | None] = {}
        # each part's term, its defined name or the part written out, kept until every place
        # that holds the part has read it: a chain held once keeps the text of its top alone
        self.terms: dict[int, str] = {}
        self.unread = dict(holders)
        self.definitions: list[str] = []
        # the lists the path reads: they read their parts by name, as often as they need, and
        # define what they write once in the program's own definitions
        self.lists = lists
        lists.named, lists.type_of, lists.definitions = self._named, self.type_of, self.definitions
        for node in order:
            self.types[id(node)] = self._result(node)
        read = self._read_by_forms(order)
        # each part comes after the parts it holds (see `distinct`), so their terms are written
        # before it, and no part waits on Python's stack for its operands
        for node in order:
            define = holders[id(node)] > 1 or id(node) in read
            self.terms[id(node)] = self._written(node, define=define)

    def assertion(self, fork: Branch) -> str:
        """The condition as the run met it: the side it took decides the negation."""
        condition = self.term(fork.expression)
        return f"(assert {condition})" if fork.taken else f"(assert (not {condition}))"

    def term(self, expression: Expression) -> str:
        """One condition or a part of one: a leaf by its constant, a defined part by its name,
        any other written out.

        Each place that holds a part reads its term once, and the last read lets it go.
        """
        name = self.leaves.named(expression)
        if name is not None:
            return self.leaves.constants[name]
        if not isinstance(expression, list):
            return _leaf(expression)
        key = id(expression)
        self.unread[key] -= 1
        return _read(self.terms[key] if self.unread[key] else self.terms.pop(key), expression)

    def _named(self, part: Expression) -> str:
        """A part's term as a list reads it: a leaf's constant, a literal, or a defined part's
        name, which no read lets go."""
        name = self.leaves.named(part)
        if name is not None:
            return self.leaves.constants[name]
        return _read(self.terms[id(part)], part) if isinstance(part, list) else _leaf(part)

    def type_of(self, term: Expression) -> type | None:
        """The type of a term's value, as Python has it, or None when nothing says.

        A leaf has the type the seed bound, a literal its own, and an
        operation the type `RESULTS` gives its head.
        """
        if self.leaves.holds(term):
            return self.leaves.kind(term)
        if isinstance(term, list):
            return self.types[id(term)]
        if isinstance(term, str):
            return str
        return None if term is None else type(term)

    def _result(self, node: Node) -> type | None:
        """The type of an operation's value, its operands already typed. A part that builds or
        reads a tracked list is typed by the lists (see ``ListTerms.result``)."""
        head, *operands = node
        self.lists.infer(node, self.types)
        if self.lists.involves(node):
            return self.lists.result(node)
        if not isinstance(head, str) or head not in RESULTS:
            return None
        result = RESULTS[head]
        return result if result is not None else self._kind(head, operands)

    def _operands_type(self, operands: list[Expression]) -> type | None:
        """The type of an operation's operands, or None when none of them says.

        Python's own operators take two operands of one type here, so the
        first that says decides it. A bool gives way to any other type, as
        Python's bool meets an int as the int 1 or 0.
        """
        kinds = [kind for part in operands if (kind := self.type_of(part))]
        return next((kind for kind in kinds if kind is not bool), kinds[0] if kinds else None)

    def _kind(self, head: str, operands: list[Expression]) -> type | None:
        """The type an operation works on: its operands', with a bool read as the int 1 or 0.

        Two bools stay bools only under an operator bool has of its own, such
        as `&` or `==`; `+` or `<` on them works on the ints they are.
        """
        kind = self._operands_type(operands)
        return int if kind is bool and (head, bool) not in OPERATORS else kind

    def _read_by_forms(self, order: list[Node]) -> set[int]:
        """The parts a form reads: an operand of a form, a piece, or an order on strings."""
        read: set[int] = set()
        for node in order:
            head, *operands = node
            if self.lists.involves(node):
                read |= {id(part) for part in self.lists.operands(node)}
            elif head in FORMS or head in POSITIONED or self._orders_strings(node):
                read |= {id(part) for part in operands if isinstance(part, list)}
        return read

    def _orders_strings(self, node: Node) -> bool:
        head, *operands = node
        return head in STRING_ORDERS and self._operands_type(operands) is str

    def _written(self, node: Node, *, define: bool) -> str:
        """A part's term, its own parts already written: its name if it is defined, else itself.

        A part to define is defined once, by name, when it has a sort to define it by. A
        tracked list has no term of its own: its reads and its length do.
        """
        kind = self.types[id(node)]
        if kind is TrackedList:
            self.lists.build(node)
            return ""
        involves = self.lists.involves(node)
        operation = self.lists.scalar(node, kind) if involves else self._operation(node)
        sort = None if kind is None or not define else _DEFINED_SORTS.get(kind)
        if sort is None:
            return operation
        name = f"e!{len(self.definitions)}"
        self.definitions.append(f"(define-fun {name} () {sort} {operation})")
        return name

    def _operation(self, node: Node) -> str:
        """An operation on its operands, as the form, the order or the operator that means it."""
        head, *operands = node
        if not isinstance(head, str):
            raise ValueError(f"pyct cannot render {head}: nothing encodes it yet")
        if (positioned := POSITIONED.get(head)) is not None:
            term, *positions = operands
            return positioned(self.term(term), *(_position(part) for part in positions))
        kind = self._kind(head, operands)
        rendered = [self._operand(part, kind) for part in operands]
        if (form := FORMS.get(head)) is not None:
            return form(*rendered)
        if head in STRING_ORDERS and kind is str:
            return _string_order(head, operands, rendered)
        return f"({_operator(head, kind)} {' '.join(rendered)})"

    def _operand(self, part: Expression, kind: type | None) -> str:
        """An operand's term, where an operation on ints reads a bool as the int 1 or 0."""
        if kind is int and isinstance(part, bool):
            return "1" if part else "0"
        term = self.term(part)
        if kind is int and self.type_of(part) is bool:
            return f"(ite {term} 1 0)"
        return term


def _read(term: str, part: Expression) -> str:
    """A part's term where a condition reads it. A tracked list and a read of an item no term
    holds, a None or a list inside, write none: no condition core records reads one whole."""
    if not term:
        raise UnencodedError(f"pyct cannot render {part}: it is no value a condition reads")
    return term


def _leaf(leaf: str | int | float | bool | None) -> str:
    """A number, a truth value or a string literal. A negative number is a subtraction."""
    if leaf is None:
        raise ValueError("pyct cannot render a missing bound outside a slice")
    if isinstance(leaf, float):
        # a list display holds a float as itself, and no read of one reaches a fork yet
        raise ValueError(f"pyct cannot render {leaf!r}: nothing solves a float yet")
    if isinstance(leaf, bool):
        return "true" if leaf else "false"
    if isinstance(leaf, int):
        return f"(- {-leaf})" if leaf < 0 else str(leaf)
    return encode(value_of(leaf))


def _position(part: Expression) -> int | None:
    """A position in a piece, as the plain int it is, or None for a slice's missing bound."""
    if part is None or (isinstance(part, int) and not isinstance(part, bool)):
        return part
    raise ValueError(f"pyct cannot render {part} as a position: core writes a plain int there")


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


def _literal(part: Expression) -> str | None:
    """The value of an operand that is a string literal, or None for any other operand."""
    return value_of(part) if isinstance(part, str) and is_literal(part) else None


def _operator(head: str, kind: type | None) -> str:
    """How SMT-LIB spells the operator a condition leads with, on operands of that type."""
    operator = OPERATORS.get((head, kind)) if kind is not None else None
    if operator is None:
        on = "anything" if kind is None else kind.__name__
        raise ValueError(f"pyct cannot render {head} on {on}: nothing encodes it yet")
    return operator
