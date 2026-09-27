"""A path of forks written out as the SMT-LIB program cvc5 reads."""

from collections.abc import Callable, Collection, Mapping
from functools import partial

from pyct.binding.shapes import ListShape
from pyct.core.branch import Branch, Expression
from pyct.solver import floats
from pyct.solver.answer_size import longest_string
from pyct.solver.checks import CHECKS, check, checks_by_string
from pyct.solver.dag import Node, distinct
from pyct.solver.declared import Leaves, Program, symbols
from pyct.solver.heads import (
    BOUNDED,
    FORMS,
    INDEXED,
    MEMBERSHIPS,
    OPERATORS,
    POSITIONED,
    POSITIONS_FROM,
    RESULTS,
    SORTS,
    STRING_ORDERS,
    WORKS_ON,
)
from pyct.solver.joined import joined
from pyct.solver.letters import Key, Spellings, fixed_position
from pyct.solver.lists import ListTerms, Origin, TrackedList, UnencodedError
from pyct.solver.literals import leaf_term, plain_operand, string_order
from pyct.solver.recased import TO_DECLARE, Declared
from pyct.solver.splits import SPLITS
from pyct.solver.symbols import leaf_sort


def program(
    prefix: tuple[Branch, ...],
    leaves: Mapping[str, type],
    lists: Mapping[str, ListShape] | Origin | None = None,
    *,
    finite: Collection[str] = (),
    cores: bool = False,
) -> Program:
    """The whole little program for a path, with the table that reads its answer back.

    What to declare, what to define, what to assert, what to ask. Only the
    leaves the prefix mentions are declared, so the answer names nothing the
    path did not depend on. ``leaves`` names each leaf as ``pyct.binding``
    does, and ``symbol`` names its constant. ``lists`` names each tracked list
    with its shape, or is the input whose path this is (``Origin``): its lists,
    its values, which settle a list cut at clamps the path leaves open, and the
    instant writing must end by. Two pieces of one string side by side are first
    written as the one piece they make (see `joined`), and a part of the
    conditions written more than once is defined once before the assertions (see
    `_Program`). Each float leaf in ``finite`` that the prefix names is held to a
    finite double, and each bound a form is exact inside is held (see `Program`).
    With ``cores``, each of those finite assertions is named for the leaf's
    symbol and cvc5 is asked to dump the unsat core, so an unsat says which of
    them it rests on; that slows some sat answers, so only a program asked after
    an unsat does it. Without ``Origin.bounded`` the bounds are left out, and
    each form past its bound is only what Python could give there (see
    ``floats.floor_division``).
    """
    origin = lists if isinstance(lists, Origin) else Origin(shapes=lists or {})
    prefix, order, holders, named = _path(prefix, leaves, origin.shapes)
    constants = {name: f"|{symbol}|" for name, symbol in named.items() if name in leaves}
    # a leaf no sort declares is named before any term on it is written
    declared = [(constant, leaf_sort(name, leaves[name])) for name, constant in constants.items()]
    terms = ListTerms(origin.shapes, {name: named[name] for name in named if name in origin.shapes})
    terms.learn(prefix)
    terms.start_from(origin, constants)
    body = _Program(Leaves(leaves, constants, origin.shapes), order, holders, prefix, terms)
    held = [name for name in constants if name in finite and leaves[name] is float]
    finites = [floats.held_finite(constants[name], named[name] if cores else None) for name in held]
    text = _text(prefix, body, declared, finites, cores=bool(held and cores))
    by_symbol = {symbol: name for name, symbol in named.items() if name in leaves}
    listed = terms if terms.declared else None
    return Program(
        text,
        by_symbol,
        listed,
        narrowed=terms.narrowed,
        held=terms.held,
        bounded=bool(body.bounds),
    )


def _path(
    prefix: tuple[Branch, ...], leaves: Mapping[str, type], shapes: Mapping[str, ListShape]
) -> tuple[tuple[Branch, ...], list[Node], dict[int, int], dict[str, str]]:
    """The path as the program writes it: joins of string pieces written as one, each distinct
    part in order with how many places hold it, and each leaf and list it names by symbol."""
    seed = Leaves(kinds=leaves, constants={}, lists=shapes)
    listed = ListTerms(shapes, {}).listed(distinct(prefix, seed.holds)[0])
    prefix = joined(prefix, seed.holds, lambda part: id(part) in listed or part in shapes)
    order, holders = distinct(prefix, seed.holds)
    return prefix, order, holders, symbols(prefix, order, seed)


def _text(
    prefix: tuple[Branch, ...],
    body: "_Program",
    declared: list[tuple[str, str]],
    finites: list[str],
    *,
    cores: bool,
) -> str:
    """The program's lines, in the order cvc5 reads them: each leaf and each list's parts
    declared before any term on them, the leaves held finite, the definitions, what the lists
    and the path assert, and what to ask for."""
    terms = body.lists
    lines = ["(set-option :dump-unsat-cores true)"] if cores else []
    lines.append("(set-logic ALL)")
    lines += [f"(declare-const {constant} {sort})" for constant, sort in declared]
    lines += [longest_string(constant) for constant, sort in declared if sort == SORTS[str]]
    lines += [f"(declare-const {name} {sort})" for name, sort in terms.declared.items()]
    lines += finites
    lines += body.definitions + [f"(assert {bound})" for bound in body.bounds if body.bounded]
    lines += terms.assertions()
    lines += [body.assertion(fork) for fork in prefix]
    lines.append("(check-sat)")
    lines += [f"(get-value ({constant}))" for constant, _ in declared]
    lines += [f"(get-value ({name}))" for name in terms.asked()]
    return "\n".join(lines) + "\n"


def float_leaves(
    prefix: tuple[Branch, ...],
    leaves: Mapping[str, type],
    lists: Mapping[str, ListShape] | None = None,
) -> frozenset[str]:
    """The float leaves a fork of the prefix names: those its first ask holds finite."""
    if float not in leaves.values():
        return frozenset()
    _, _, _, named = _path(prefix, leaves, lists or {})
    return frozenset(name for name in named if leaves.get(name) is float)


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
        leaves: Leaves,
        order: list[Node],
        holders: dict[int, int],
        prefix: tuple[Branch, ...],
        lists: ListTerms,
    ) -> None:
        self.leaves = leaves
        # whether each bound a form is exact inside is held (see `_bounded`)
        self.bounded = lists.source.bounded
        self.types: dict[int, type | None] = {}
        # each part's term, its defined name or the part written out, kept until every place
        # that holds the part has read it: a chain held once keeps the text of its top alone
        self.terms: dict[int, str] = {}
        self.unread = dict(holders)
        self.definitions: list[str] = []
        self.facts: set[str] = set()
        self.bounds: list[str] = []
        # each tuple's item terms, read once as the tuple is reached
        self.tuples: dict[int, tuple[str, ...]] = {}
        # the lists the path reads: they read their parts by name, as often as they need, and
        # define what they write once in the program's own definitions
        self.lists = lists
        lists.named, lists.type_of, lists.definitions = self._named, self.type_of, self.definitions
        lists.constant = self._constant
        for node in order:
            self.types[id(node)] = self._result(node)
        # the strings read at fixed positions, each written once as its first letters (see
        # `letters`), and the letters' names once written
        self.spellings = Spellings(order, prefix, self._string)
        # the checks each string is read by: a string one check reads is asked as a membership
        self.checked = checks_by_string(order, self._string)
        self._write_each(order, holders, self._read_by_forms(order))

    def _write_each(self, order: list[Node], holders: dict[int, int], read: set[int]) -> None:
        """Each part's term, in order. Each part comes after the parts it holds (see
        `distinct`), so their terms are written before it, and no part waits on Python's stack
        for its operands."""
        for node in order:
            if (kind := self.types[id(node)]) in (tuple, range):
                # no term of its own: a search reads a tuple's items, a membership or an equality
                # a range's Ints
                item_term = self.term if kind is tuple else partial(self._operand, kind=int)
                self.tuples[id(node)] = tuple(item_term(item) for item in node[1:])
                continue
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
            return leaf_term(expression)
        key = id(expression)
        self.unread[key] -= 1
        return _read(self.terms[key] if self.unread[key] else self.terms.pop(key), expression)

    def _named(self, part: Expression) -> str:
        """A part's term as a list reads it: a leaf's constant, a literal, or a defined part's
        name, which no read lets go.

        A list reads only its own operands, whose terms stay until it is written; a part whose
        term was let go is refused as a miss rather than a crash."""
        constant = self._constant(part)
        if constant is not None:
            return constant
        if not isinstance(part, list):
            return leaf_term(part)
        if id(part) not in self.terms:
            raise UnencodedError(f"pyct cannot render {part}: its term was already let go")
        return _read(self.terms[id(part)], part)

    def _constant(self, part: Expression) -> str | None:
        """The constant of the leaf a part is, or None for any other part."""
        name = self.leaves.named(part)
        return None if name is None else self.leaves.constants[name]

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
        first that says decides it, but for two numbers: a float makes the
        operation a float's, as Python converts an int that meets one. A bool
        gives way to any other type, as Python's bool meets an int as the int
        1 or 0.
        """
        kinds = [kind for part in operands if (kind := self.type_of(part))]
        if float in kinds:
            return float
        return next((kind for kind in kinds if kind is not bool), kinds[0] if kinds else None)

    def _kind(self, head: str, operands: list[Expression]) -> type | None:
        """The type an operation works on: its operands', a bool read as the int 1 or 0 but under
        an operator bool has of its own, such as `&` or `==`, and a range's by its ints."""
        kind = WORKS_ON.get(head) or self._operands_type(operands)
        if kind is range and head in MEMBERSHIPS:
            return int
        return int if kind is bool and (head, bool) not in OPERATORS else kind

    def _read_by_forms(self, order: list[Node]) -> set[int]:
        """The parts a form reads: an operand of a form, a check, a piece, a split, a declared
        string, or an order on strings."""
        read: set[int] = set()
        for node in order:
            if self.lists.involves(node):
                read |= {id(part) for part in self.lists.operands(node)}
            elif (
                self._form(node) is not None
                or _read_by_a_form(node[0])
                or self._orders_strings(node)
            ):
                read |= {id(part) for part in node[1:] if isinstance(part, list)}
        return read

    def _form(self, node: Node) -> Callable[..., str] | None:
        """The form that writes an operation on the type it works on, or None for an operator.

        A form exact only inside a bound writes its term, and its bound is held once.
        """
        head, *operands = node
        if not isinstance(head, str):
            return None
        kind = self._kind(head, operands)
        bounded = None if kind is None else BOUNDED.get((head, kind))
        if bounded is not None:
            return partial(self._bounded, bounded)
        return None if kind is None else FORMS.get((head, kind))

    def _bounded(self, form: Callable[..., tuple[str, str]], *operands: str) -> str:
        """A bounded form's term, and its bound noted once.

        A program that holds its bounds writes the form exact everywhere; one
        that leaves them out writes it past its bound as a double declared for
        this term alone.
        """
        if self.bounded:
            term, bound = form(*operands)
        else:
            past = f"e!{len(self.definitions)}"
            self.definitions.append(f"(declare-const {past} Float64)")
            term, bound = form(*operands, past)
        if bound not in self.bounds:
            self.bounds.append(bound)
        return term

    def _orders_strings(self, node: Node) -> bool:
        head, *operands = node
        return head in STRING_ORDERS and self._operands_type(operands) is str

    def _written(self, node: Node, *, define: bool) -> str:
        """A part's term, its own parts already written: its name if it is defined, else itself.

        A part to define is defined once, by name, when it has a sort to define it by. A
        split's term is the string it splits, for its pieces to read, and a string no term
        writes is declared (see `_declared`). A tracked list has no term of its own: its reads
        and its length do.
        """
        kind = self.types[id(node)]
        if kind is TrackedList:
            self.lists.build(node)
            return ""
        if kind is list:
            return self.term(node[1])
        involves = self.lists.involves(node)
        operation = self.lists.scalar(node, kind) if involves else self._operation(node)
        sort = None if kind is None or not define else SORTS.get(kind)
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
            read = self._position if head in INDEXED else plain_operand
            return positioned(self.term(term), *(read(part) for part in positions))
        kind = self._kind(head, operands)
        if (form := self._form(node)) is not None:
            return form(*self._rendered(head, operands, kind))
        rendered = [self._operand(part, kind) for part in operands]
        if (declared := TO_DECLARE.get(head)) is not None:
            return self._declared(declared, *rendered)
        if head in CHECKS:
            alone = self.checked.get(self._string(operands[0])) == {head}
            answer, fact = check(head, *rendered, alone=alone)
            self._hold(fact)
            return answer
        if head in STRING_ORDERS and kind is str:
            return string_order(head, operands, rendered)
        return f"({_operator(head, kind)} {' '.join(rendered)})"

    def _rendered(self, head: str, operands: list[Expression], kind: type | None) -> list[object]:
        """Each operand's term; past the operands a search or a replace reads as terms, each
        position as `_position` reads it, and a tuple as its items' terms."""
        first = POSITIONS_FROM.get(head, len(operands)) if kind is str else len(operands)
        terms: list[object] = [self._operand_or_items(part, kind) for part in operands[:first]]
        return terms + [self._position(part) for part in operands[first:]]

    def _operand_or_items(self, part: Expression, kind: type | None) -> str | tuple[str, ...]:
        """An operand's term, or a tuple's or a range's items' terms, which is all either has."""
        if isinstance(part, list) and self.type_of(part) in (tuple, range):
            return self.tuples[id(part)]
        return self._operand(part, kind)

    def _position(self, part: Expression) -> int | str | None:
        """A position a form reads: a plain int or bool as the int, None for a missing one, and
        a tracked one by its Int term."""
        if part is None or isinstance(part, int):
            return None if part is None else int(part)
        return self.term(part)

    def _operand(self, part: Expression, kind: type | None) -> str:
        """An operand's term, where an operation on numbers reads a bool as the int 1 or 0, and
        one on floats reads an int, a bool among them, as the double Python converts it to.

        A bool reaches a float operation under `/` alone, which divides two ints as floats.
        """
        number = kind is int or kind is float
        if number and isinstance(part, bool):
            term, whole = ("1" if part else "0"), True
        else:
            term = self.term(part)
            whole = number and self.type_of(part) in (int, bool)
            if number and self.type_of(part) is bool:
                term = f"(ite {term} 1 0)"
        return floats.from_int(term) if kind is float and whole else term

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
        (index,) = (plain_operand(part) for part in positions)
        if not isinstance(index, int):
            raise ValueError(f"pyct cannot render piece {index} of a split: core writes an int")
        operands = tuple(plain_operand(part) for part in split[2:])
        piece, there = SPLITS[str(split[0])](self.term(split), operands, index)
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


def _read(term: str, part: Expression) -> str:
    """A part's term where a condition reads it. A tracked list and a read of an item no term
    holds, a None or a list inside, write none: no condition core records reads one whole."""
    if not term:
        raise UnencodedError(f"pyct cannot render {part}: it is no value a condition reads")
    return term


def _operator(head: str, kind: type | None) -> str:
    """How SMT-LIB spells the operator a condition leads with, on operands of that type."""
    operator = OPERATORS.get((head, kind)) if kind is not None else None
    if operator is None:
        on = "anything" if kind is None else kind.__name__
        raise ValueError(f"pyct cannot render {head} on {on}: nothing encodes it yet")
    return operator
