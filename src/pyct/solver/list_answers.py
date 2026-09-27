"""What cvc5 answered about the tracked lists of a path, as one answer per list.

Each list the path reads comes back at the length cvc5 chose, with the arrays its items come
from. Which positions a fork read is worked out here, in Python: each list the path built is
built again from the answered lengths and the values of its positions, by Python's own `+`,
`*` and slicing, over marks that say where each item came from. A position no fork read keeps
what the input had (see ``binding.shapes.resized``).
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from pyct.binding.shapes import ArrayValue, ListAnswer
from pyct.core.branch import Expression
from pyct.solver.answer import SolverAnswerError
from pyct.solver.lists import ListTerms

# where an item of a list the path built came from: a list the seed names, the positions of the
# list inside it, and the position in that list; or None for an item a display holds
type _Mark = tuple[str, tuple[int, ...], int] | None


def list_answers(lists: ListTerms, model: Mapping[str, object]) -> dict[str, ListAnswer]:
    """Each list the path names, and each list inside one it reads, with its answer, named as
    the seed names it."""
    answering = _Answering(lists, model)
    read = answering.read()
    answers: dict[str, ListAnswer] = {}
    for name, positions in answering.lists():
        answers[_named(name, positions)] = answering.answer(name, positions, read)
    return answers


def _count(value: object) -> int:
    """A length or a count the answer holds, which cvc5 always writes as a number."""
    if not isinstance(value, int):
        raise SolverAnswerError(f"cvc5 answered a length that is not a number: {value!r}")
    return value


def _named(name: str, positions: tuple[int, ...]) -> str:
    """The name a list inside a list goes by: its access, as JSON."""
    if not positions:
        return name
    access: Expression = name if not name.startswith("[") else json.loads(name)
    for at in positions:
        access = ["[]", access, at]
    return json.dumps(access)


class _Answering:
    """One answer, read list by list."""

    def __init__(self, lists: ListTerms, model: Mapping[str, object]) -> None:
        self.terms = lists
        self.model = model
        self.marks: dict[int, list[_Mark]] = {}
        # the marks of each list the seed names, by name and the positions of a list inside it
        self.stored: dict[tuple[str, tuple[int, ...]], list[_Mark]] = {}

    def lists(self) -> list[tuple[str, tuple[int, ...]]]:
        """Every list the program declared: each the seed names, and each inside one a part
        reads."""
        named = [(name, ()) for name in self.terms.symbols if self._declared(name, (), "len")]
        inside = {
            (name, positions)
            for name, places, _ in self.terms.stored.values()
            if (positions := self._places(name, places)) is not None
        }
        return named + sorted(inside - set(named))

    def _places(self, name: str, places: tuple[Expression, ...]) -> tuple[int, ...] | None:
        """The positions that reach a list inside, each as the answer has it: a position from
        the end counted back from the answered length of the list it is inside."""
        positions: list[int] = []
        for place in places:
            at = self._number(place)
            if at is None:
                return None
            if at < 0:
                at += _count(self._value(name, tuple(positions), "len"))
            positions.append(at)
        return tuple(positions)

    def answer(
        self,
        name: str,
        positions: tuple[int, ...],
        read: Mapping[tuple[str, tuple[int, ...]], set[int]],
    ) -> ListAnswer:
        """One list's length, arrays and the positions a fork read."""
        length = self._value(name, positions, "len")
        arrays = {
            kind: array
            for kind in ("int", "str")
            if isinstance(array := self._value(name, positions, kind), ArrayValue)
        }
        found = read.get((name, positions), set())
        return ListAnswer(length=_count(length), arrays=arrays, read=frozenset(found))

    def read(self) -> dict[tuple[str, tuple[int, ...]], set[int]]:
        """The positions each read on the path took, by the list the seed names it came from."""
        for node in self.terms.built:
            self.marks[id(node)] = self._built(node)
        read: dict[tuple[str, tuple[int, ...]], set[int]] = {}
        for listed, position in self.terms.reads:
            marks = self._marks(listed)
            at = self._number(position)
            if at is not None and -len(marks) <= at < len(marks):
                mark = marks[at]
                if mark is not None:
                    read.setdefault((mark[0], mark[1]), set()).add(mark[2])
        return read

    def _marks(self, part: Expression) -> list[_Mark]:
        name = self.terms.leaf(part)
        if name is not None:
            return self._stored(name, ())
        return self.marks[id(part)]

    def _built(self, node: list[Expression]) -> list[_Mark]:
        """A list the path built, built again over marks, by Python's own operations."""
        head, *operands = node
        if head == "[]":
            name, places, _ = self.terms.stored[id(node)]
            positions = self._places(name, places)
            return [] if positions is None else self._stored(name, positions)
        if head == "[,]":
            return [None] * len(operands)
        if head == "+":
            return self._marks(operands[0]) + self._marks(operands[1])
        if head == "*":
            times = next(part for part in operands if type(part) is int)
            listed = next(part for part in operands if type(part) is not int)
            return self._marks(listed) * _count(times)
        bounds = [self._number(part) for part in operands[1:]]
        return self._marks(operands[0])[slice(*bounds)]

    def _stored(self, name: str, positions: tuple[int, ...]) -> list[_Mark]:
        """The marks of a list the seed names, or of a list inside one: made once, since a
        walk over it reads every one."""
        key = (name, positions)
        if key not in self.stored:
            length = self._value(name, positions, "len")
            self.stored[key] = [(name, positions, at) for at in range(_count(length))]
        return self.stored[key]

    def _number(self, part: Expression) -> int | None:
        """A position or a bound's value: a number as written, or the value cvc5 gave its term."""
        if part is None or (isinstance(part, int) and not isinstance(part, bool)):
            return part
        value = self.model.get(self.terms.named(part).strip("|"))
        return value if isinstance(value, int) else None

    def _declared(self, name: str, positions: tuple[int, ...], part: str) -> bool:
        return self._symbol(name, positions, part) in self.model

    def _symbol(self, name: str, positions: tuple[int, ...], part: str) -> str:
        return f"{self.terms.symbols[name]}.{'rows.' * len(positions)}{part}"

    def _value(self, name: str, positions: tuple[int, ...], part: str) -> object:
        """A list's length or array, read from the model at the positions that reach it."""
        value = self.model.get(self._symbol(name, positions, part))
        for at in positions:
            value = value.at(at) if isinstance(value, ArrayValue) else None
        return value
