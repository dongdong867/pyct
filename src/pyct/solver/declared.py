"""What a path's program declares, and how its answer is read back by name.

A leaf is an int or a str the seed names on its own: a parameter, or a value inside a dict. A
list the seed names is a leaf too, declared as its length and its items (see ``lists``). Each
gets a symbol, and the answer names each back by it.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass, field

from pyct.binding.bind import access_name
from pyct.binding.shapes import ListAnswer, ListShape
from pyct.core.branch import Branch, Expression
from pyct.solver.answer import SolverAnswerError
from pyct.solver.dag import Node
from pyct.solver.heads import SORTS
from pyct.solver.list_answers import list_answers
from pyct.solver.lists import ListTerms, TrackedList

# what opens a string literal in an expression: repr writes one in either quote, and a
# parameter name holds neither
_QUOTES = ("'", '"')


def is_literal(leaf: str) -> bool:
    """Whether a str leaf is a string literal, which opens with a quote, or a parameter name."""
    return leaf.startswith(_QUOTES)


def value_of(literal: str) -> str:
    """The str a string literal, written as repr writes it, holds."""
    value = ast.literal_eval(literal)
    if not isinstance(value, str):
        raise ValueError(f"pyct cannot render {literal}: it is not a string literal")
    return value


@dataclass(frozen=True)
class Leaves:
    """The seed's leaves by name, with their types and the constant each mentioned one gets,
    and the lists it names, with their shapes."""

    kinds: Mapping[str, type]
    constants: Mapping[str, str]
    lists: Mapping[str, ListShape] = field(default_factory=dict)
    # what `named` answered for each list part, by its identity: a path reads each part many
    # times, and an access is written out as JSON to be looked up
    _names: dict[int, str | None] = field(default_factory=dict, compare=False)

    def named(self, part: Expression) -> str | None:
        """The name of the leaf a part of a condition is, or None for a literal or an operation.

        A parameter is its bare name. A value inside one is its access, which
        reads as an operation does: only an access to one of the seed's own
        leaves or lists is a value, and any other is an operation on a tracked value,
        such as an item of a list. Which steps an access takes is binding's to say
        (``access_name``).
        """
        if isinstance(part, str):
            return None if is_literal(part) else part
        if not isinstance(part, list):
            return None
        if id(part) not in self._names:
            name = access_name(part)
            known = name in self.kinds or name in self.lists
            self._names[id(part)] = name if known else None
        return self._names[id(part)]

    def holds(self, part: Expression) -> bool:
        """Whether a part is one of the seed's leaves, which a condition names and never opens."""
        return self.named(part) is not None

    def kind(self, part: Expression) -> type | None:
        """The type of the leaf a part is, or None for anything else."""
        name = self.named(part)
        if name is None:
            return None
        return TrackedList if name in self.lists else self.kinds.get(name)


@dataclass(frozen=True)
class Program:
    """The SMT-LIB program for one path, and the leaf each constant it declares stands for.

    ``names_by_symbol`` holds each leaf's name, keyed by its constant's
    symbol without the bars, which is how a model names it back. ``lists`` is what the
    program declared for the lists the path reads, which reads their answers back.
    """

    text: str
    names_by_symbol: Mapping[str, str]
    lists: ListTerms | None = None
    # whether the program holds the answer to more than the path: clamps settled as the input
    # had them, so unsat is only unknown; or a repeated list's length held
    narrowed: bool = False
    held: bool = False

    def read(self, model: Mapping[str, object]) -> dict[str, object]:
        """A model cvc5 wrote by constant, named by the leaves the constants were declared for,
        and each list's answer by the list's name.

        A symbol the program did not declare is ``SolverAnswerError``, as any
        value line pyct cannot read is: a guess would hand back a wrong input.
        """
        listed = set() if self.lists is None else self.lists.answered()
        unknown = [s for s in model if s not in self.names_by_symbol and s not in listed]
        if unknown:
            named = ", ".join(unknown)
            raise SolverAnswerError(
                f"cvc5 answered about names the program did not declare: {named}"
            )
        read: dict[str, object] = {
            self.names_by_symbol[symbol]: value
            for symbol, value in model.items()
            if symbol in self.names_by_symbol
        }
        answers: dict[str, ListAnswer] = {}
        if self.lists is not None:
            answers = list_answers(self.lists, model)
        return {**read, **answers}


def symbols(prefix: tuple[Branch, ...], order: list[Node], seed: Leaves) -> dict[str, str]:
    """The symbol of each leaf and list the prefix names, in the order the seed bound them."""
    parts = [fork.expression for fork in prefix] + [part for node in order for part in node[1:]]
    named = {name for part in parts if (name := seed.named(part)) is not None}
    unknown = sorted(named - set(seed.kinds) - set(seed.lists))
    if unknown:
        raise ValueError(f"the path names what the seed does not bind: {', '.join(unknown)}")
    every = [*seed.kinds, *seed.lists]
    return {name: symbol(name, index) for index, name in enumerate(every) if name in named}


def symbol(name: str, index: int) -> str:
    """A leaf's symbol, written inside bars: ``arg.<name>`` for a name that is an identifier.

    The prefix keeps every symbol apart from the solver's own words, which
    a parameter may be named as, ``div`` say: cvc5 refuses to declare one,
    bars or not. Each character past ASCII is written as its UTF-8 bytes,
    ``%C3%A9`` for ``é``, so the program stays ASCII. Any other name is
    ``leaf.<n>``, n its position among the seed's leaves: a value inside an
    argument is named by its access, which holds brackets, quotes, and any
    character a key holds, ``|`` and the backslash among them, which not
    even a quoted symbol can.
    """
    if not name.isidentifier():
        return f"leaf.{index}"
    written = "".join(
        character if character.isascii() else "".join(f"%{byte:02X}" for byte in character.encode())
        for character in name
    )
    return f"arg.{written}"


def sort_of(name: str, kind: type) -> str:
    sort = SORTS.get(kind)
    if sort is None:
        raise ValueError(f"pyct cannot declare {name}: nothing solves a {kind.__name__} yet")
    return sort
