"""A path of forks written out as the SMT-LIB program cvc5 reads."""

import ast
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass

from pyct.binding.bind import access_name
from pyct.core.branch import Branch, Expression
from pyct.solver import floats
from pyct.solver.answer import SolverAnswerError
from pyct.solver.checks import CHECKS
from pyct.solver.dag import Node, distinct
from pyct.solver.heads import FORMS, OPERATORS, POSITIONED, RESULTS, SORTS, STRING_ORDERS
from pyct.solver.joined import joined
from pyct.solver.letters import Key, Spellings, fixed_position
from pyct.solver.recased import TO_DECLARE, Declared
from pyct.solver.splits import SPLITS
from pyct.solver.strings import above, below, encode
from pyct.solver.symbols import leaf_sort, leaf_symbol

# what opens a string literal in an expression: repr writes one in either quote, and a
# parameter name holds neither
_QUOTES = ("'", '"')

# the sort of a part defined once, by the type of its value
_DEFINED_SORTS: Mapping[type, str] = {**SORTS, bool: "Bool"}

# what names the assertion that holds a float leaf finite, before the leaf's symbol, so the
# unsat core cvc5 dumps says which leaves an unsat rests on. `!` is in no symbol, so the
# assertion's name never meets a constant
FINITE = "finite!"


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

    def holds(self, part: Expression) -> bool:
        """Whether a part is one of the seed's leaves, which a condition names and never opens."""
        return self.named(part) is not None

    def kind(self, part: Expression) -> type | None:
        """The type of the leaf a part is, or None for anything else."""
        name = self.named(part)
        return None if name is None else self.kinds.get(name)


@dataclass(frozen=True)
class Program:
    """The SMT-LIB program for one path, and the leaf each constant it declares stands for.

    ``names_by_symbol`` holds each leaf's name, keyed by its constant's
    symbol without the bars, which is how a model names it back.
    """

    text: str
    names_by_symbol: Mapping[str, str]

    def read(self, model: Mapping[str, object]) -> dict[str, object]:
        """A model cvc5 wrote by constant, named by the leaves the constants were declared for.

        A symbol the program did not declare is ``SolverAnswerError``, as any
        value line pyct cannot read is: a guess would hand back a wrong input.
        """
        unknown = [symbol for symbol in model if symbol not in self.names_by_symbol]
        if unknown:
            named = ", ".join(unknown)
            raise SolverAnswerError(
                f"cvc5 answered about names the program did not declare: {named}"
            )
        return {self.names_by_symbol[symbol]: value for symbol, value in model.items()}


def program(
    prefix: tuple[Branch, ...],
    leaves: Mapping[str, type],
    *,
    finite: Collection[str] = (),
    cores: bool = False,
) -> Program:
    """The whole little program for a path, with the table that reads its answer back.

    What to declare, what to define, what to assert, what to ask. Only the
    leaves the prefix mentions are declared, so the answer names nothing the
    path did not depend on. ``leaves`` names each leaf as ``pyct.binding``
    does, and ``leaf_symbol`` names its constant. Two pieces of one string side by
    side are first written as the one piece they make (see `joined`), and a
    part of the conditions written more than once is defined once before the
    assertions (see `_Program`). Each float leaf in ``finite`` that the
    prefix names is held to a finite double. With ``cores``, each of those
    assertions is named for the leaf's symbol and cvc5 is asked to dump the
    unsat core, so an unsat says which of them it rests on; that slows some
    sat answers, so only a program asked after an unsat does it.
    """
    seed = _Leaves(kinds=leaves, constants={})
    prefix = joined(prefix, seed.holds)
    order, holders = distinct(prefix, seed.holds)
    symbols = _symbols(prefix, order, seed)
    constants = {name: f"|{symbol}|" for name, symbol in symbols.items()}
    # a leaf no sort declares is named before any term on it is written
    declared = [(constant, leaf_sort(name, leaves[name])) for name, constant in constants.items()]
    body = _Program(_Leaves(kinds=leaves, constants=constants), order, holders, prefix)
    held = [name for name in constants if name in finite and leaves[name] is float]
    lines = ["(set-option :dump-unsat-cores true)"] if held and cores else []
    lines.append("(set-logic ALL)")
    lines += [f"(declare-const {constant} {sort})" for constant, sort in declared]
    lines += [_held_finite(constants[name], symbols[name] if cores else None) for name in held]
    lines += body.definitions
    lines += [body.assertion(fork) for fork in prefix]
    lines.append("(check-sat)")
    lines += [f"(get-value ({constant}))" for constant, _ in declared]
    text = "\n".join(lines) + "\n"
    return Program(text=text, names_by_symbol={symbol: name for name, symbol in symbols.items()})


def float_leaves(prefix: tuple[Branch, ...], leaves: Mapping[str, type]) -> frozenset[str]:
    """The float leaves a fork of the prefix names: those its first ask holds finite."""
    if float not in leaves.values():
        return frozenset()
    seed = _Leaves(kinds=leaves, constants={})
    prefix = joined(prefix, seed.holds)
    order, _ = distinct(prefix, seed.holds)
    return frozenset(name for name in _symbols(prefix, order, seed) if leaves[name] is float)


def _held_finite(constant: str, symbol: str | None) -> str:
    """The assertion that holds one float leaf finite, named for the leaf's symbol if given."""
    held = floats.finite(constant)
    return f"(assert {held})" if symbol is None else f"(assert (! {held} :named {FINITE}{symbol}))"


def _symbols(prefix: tuple[Branch, ...], order: list[Node], seed: _Leaves) -> dict[str, str]:
    """The symbol of each leaf the prefix names, in the order the seed bound them."""
    parts = [fork.expression for fork in prefix] + [part for node in order for part in node[1:]]
    named = {name for part in parts if (name := seed.named(part)) is not None}
    unknown = sorted(named - set(seed.kinds))
    if unknown:
        raise ValueError(f"the path names what the seed does not bind: {', '.join(unknown)}")
    return {
        name: leaf_symbol(name, index) for index, name in enumerate(seed.kinds) if name in named
    }


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
        self,
        leaves: _Leaves,
        order: list[Node],
        holders: dict[int, int],
        prefix: tuple[Branch, ...],
    ) -> None:
        self.leaves = leaves
        self.types: dict[int, type | None] = {}
        # each part's term, its defined name or the part written out, kept until every place
        # that holds the part has read it: a chain held once keeps the text of its top alone
        self.terms: dict[int, str] = {}
        self.unread = dict(holders)
        self.definitions: list[str] = []
        self.facts: set[str] = set()
        for node in order:
            self.types[id(node)] = self._result(node)
        # the strings read at fixed positions, each written once as its first letters (see
        # `letters`), and the letters' names once written
        self.spellings = Spellings(order, prefix, self._string)
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
        return self.terms[key] if self.unread[key] else self.terms.pop(key)

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
        """The type of an operation's value, its operands already typed."""
        head, *operands = node
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
        """The parts a form reads: an operand of a form, a check, a piece, a split, a declared
        string, or an order on strings."""
        read: set[int] = set()
        for node in order:
            if (
                self._form(node) is not None
                or _read_by_a_form(node[0])
                or self._orders_strings(node)
            ):
                read |= {id(part) for part in node[1:] if isinstance(part, list)}
        return read

    def _form(self, node: Node) -> Callable[..., str] | None:
        """The form that writes an operation on the type it works on, or None for an operator."""
        head, *operands = node
        if not isinstance(head, str):
            return None
        kind = self._kind(head, operands)
        return None if kind is None else FORMS.get((head, kind))

    def _orders_strings(self, node: Node) -> bool:
        head, *operands = node
        return head in STRING_ORDERS and self._operands_type(operands) is str

    def _written(self, node: Node, *, define: bool) -> str:
        """A part's term, its own parts already written: its name if it is defined, else itself.

        A part to define is defined once, by name, when it has a sort to define it by. A
        split's term is the string it splits, for its pieces to read, and a string no term
        writes is declared (see `_declared`).
        """
        kind = self.types[id(node)]
        if kind is list:
            return self.term(node[1])
        operation = self._operation(node)
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
            if isinstance(term, list) and self.type_of(term) is list:
                return self._piece(term, positions)
            if (letter := self._letter(node)) is not None:
                return letter
            return positioned(self.term(term), *(_plain(part) for part in positions))
        kind = self._kind(head, operands)
        rendered = [self._operand(part, kind) for part in operands]
        if (form := self._form(node)) is not None:
            return form(*rendered)
        if (declared := TO_DECLARE.get(head)) is not None:
            return self._declared(declared, *rendered)
        if (check := CHECKS.get(head)) is not None:
            answer, fact = check(*rendered)
            self._hold(fact)
            return answer
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

    def _declared(self, declared: Callable[[str, str], Declared], term: str) -> str:
        """A value no term writes whole: a name declared in it, of the sort the form says, held
        to the condition that makes the value Python's.

        The condition is asserted with the definitions, on every path: it
        only says what the name is, and some value always meets it.
        """
        name = f"e!{len(self.definitions)}"
        sort, value, condition = declared(name, term)
        self.definitions.append(f"(declare-const {name} {sort})")
        self.definitions.append(f"(assert {condition})")
        return value

    def _piece(self, split: Node, positions: list[Expression]) -> str:
        """A piece of a split, and the assertion that the string has it.

        The target took the piece out of the list Python built, so the piece
        is there on every input that follows the path this far.
        """
        (index,) = (_plain(part) for part in positions)
        if not isinstance(index, int):
            raise ValueError(f"pyct cannot render piece {index} of a split: core writes an int")
        plain = tuple(_plain(part) for part in split[2:])
        piece, there = SPLITS[str(split[0])](self.term(split), plain, index)
        self._hold(there)
        return piece

    def _string(self, part: Expression) -> Key | None:
        """What tells a string term from another: its leaf's name, or its part's id."""
        if self.type_of(part) is not str or not (self.leaves.holds(part) or isinstance(part, list)):
            return None
        return ("leaf", self.leaves.named(part)) if self.leaves.holds(part) else id(part)

    def _letter(self, node: Node) -> str | None:
        """What an index at a fixed position reads of a spelled string, or None for any other
        index (see `letters`). The string is spelled out on its first read."""
        at = fixed_position(node)
        string = None if at is None else self._string(node[1])
        if at is None or string is None or not self.spellings.spells(string):
            return None
        read, lines = self.spellings.read(string, at, self.term(node[1]))
        self.definitions += lines
        return read

    def _hold(self, fact: str) -> None:
        """Assert, once, a fact every input on the path meets."""
        if fact != "true" and fact not in self.facts:
            self.facts.add(fact)
            self.definitions.append(f"(assert {fact})")


def _read_by_a_form(head: Expression) -> bool:
    """Whether an operation's operands are read by a form of one head whatever their type."""
    return any(head in table for table in (CHECKS, POSITIONED, SPLITS, TO_DECLARE))


def _leaf(leaf: str | int | float | bool | None) -> str:
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


def _plain(part: Expression) -> int | str | None:
    """An operand a form takes as it is: an int or a bool, None for a slice's missing bound, or
    a string literal's str. A name is not one."""
    if part is None or isinstance(part, int):
        return part
    if isinstance(part, str) and _is_literal(part):
        return _value(part)
    raise ValueError(
        f"pyct cannot render {part} as a position, a separator or a fill: core writes a plain "
        "value there"
    )


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


def _operator(head: str, kind: type | None) -> str:
    """How SMT-LIB spells the operator a condition leads with, on operands of that type."""
    operator = OPERATORS.get((head, kind)) if kind is not None else None
    if operator is None:
        on = "anything" if kind is None else kind.__name__
        raise ValueError(f"pyct cannot render {head} on {on}: nothing encodes it yet")
    return operator
