"""The tracked dicts a path names, written for cvc5.

A dict the seed names is declared by what the path asks of it (containers-arrays-counted-keys-
and-copied-walk-keys, dict-keys-named-held-made-up-or-changed-under-a-tracked-key): a `Bool` for
each key a fork names, in the order the path first names it; an `Int` for how many of the
input's other keys stay, from the first, so a smaller dict loses them from its end; an `Int` for
how many keys pyct makes up to meet a count, for a dict whose keys are all of the type its made-
up keys are; and its size, one `Int` with one defining equation, at most 1,000,000 (answers-
hold-at-most-a-million-items).

A value a fork reads under a key says the dict holds that key, and so does a dict or a list a
fork reads under one. A tracked key names no key: `["in", "name", "prices"]` is whether it
equals a key the dict holds, whichever it is (see ``dict_keys``), and a value read under it is
the value under the key it equals.

The first ask holds the input's other keys and makes none up, so an answer keeps what the input
had where no fork asks otherwise; an unsat to it is asked again with both free. Each ask keeps a
key a walk read in its place where a fork reads the value under it (``_in_place``), so an answer
walks the dict as the path did; an unsat to that is asked once more without, and only an unsat
there is the path's (see ``cvc5``). A tracked key's lookups are functions each call reads, and
past their steps the program is given up (``Keyed``).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import cached_property

from pyct.binding.bind import access_name, leaf_name
from pyct.binding.shapes import DictShape
from pyct.core.branch import Branch, Expression
from pyct.solver.answer_size import MOST_ITEMS, longest_string
from pyct.solver.dict_keys import MISSING, Keyed, literal_key, made_up_match
from pyct.solver.lists import Origin, UnencodedError

# the type of a value each kind of value is read as: only an int or a str has a term
_VALUE_TYPES: Mapping[str, type] = {"int": int, "str": str}


class TrackedDict:
    """The type render gives a dict the seed names: it has no term of its own, only its keys,
    its size and its values do."""


@dataclass
class Tracked:
    """One dict of the path: what the path names of it, and what its program declares.

    ``named`` holds each key a fork names, by its place in the order the path first names it,
    and ``held`` those a read says the dict holds. ``counted`` says a fork reads the dict's
    size, and ``tracked`` that a fork looks a tracked key up in it: then each of the input's
    keys is named after the path's own, since a tracked key may equal any of them, and
    ``asked`` holds the keys a fork names itself.

    What a walk read at its place holds too (see ``core.dict_reads.placed``): ``walked``
    holds the input's keys a walk from the first read, and ``last`` those a walk from the last
    or popitem read; ``own`` says a walk from the first read one of the target's own keys.
    ``given`` holds the keys a lookup of a key Python shares with the target's literals names
    as read by a walk, whose place holds whether or not a fork reads the value there. A place
    matters only where a fork reads the value under the key there, or a given fact names it:
    another key there would hand out another value (see ``_in_place``).
    """

    name: str
    symbol: str
    shape: DictShape
    named: dict[object, int] = field(default_factory=dict)
    held: dict[object, None] = field(default_factory=dict)
    counted: bool = False
    tracked: bool = False
    asked: frozenset[object] = frozenset()
    walked: set[object] = field(default_factory=set)
    last: set[object] = field(default_factory=set)
    popped: set[object] = field(default_factory=set)
    given: set[object] = field(default_factory=set)
    own: bool = False

    def constant(self, part: str) -> str:
        return f"|{self.symbol}.{part}|"

    def candidates(self, typed: type | None) -> list[object]:
        """Every key of that type a tracked key may equal: the input's, then the path's own."""
        keys = [*self.shape.keys, *(key for key in self.named if key not in self.places)]
        return [key for key in keys if type(key) is typed]

    @cached_property
    def places(self) -> dict[object, int]:
        """Each of the input's keys by its place among them."""
        return {key: place for place, key in enumerate(self.shape.keys)}

    def slot(self, key: object) -> int:
        """Where a key stands among the input's keys and then the path's own: its value's
        constant is named by it."""
        places = self.places
        return places[key] if key in places else len(places) + self.named[key]

    @property
    def unnamed(self) -> list[object]:
        """The input's keys no fork names, in order: the ones ``kept`` counts from the first."""
        return [key for key in self.shape.keys if key not in self.named]

    def kind_under(self, key: object) -> str:
        """The kind of the value under a key: the input's, or an added value's."""
        places = self.places
        return self.shape.kinds[places[key]] if key in places else self.shape.fill

    @property
    def sized(self) -> bool:
        """Whether the program declares the dict's size, and with it the keys it keeps and makes
        up: a fork reads the size, or looks a tracked key up."""
        return self.counted or self.tracked


class DictTerms(Keyed):
    """The dicts of one path: what each names, the terms render reads, and what they declare.

    ``values`` is each leaf's value in the input, and ``constants`` each leaf's constant, for
    the leaves the path names. ``named`` gives the term of a part a dict reads, and
    ``type_of`` render's type of a part; render sets both.
    """

    def __init__(
        self,
        shapes: Mapping[str, DictShape],
        values: Mapping[str, object],
        constants: Mapping[str, str],
    ) -> None:
        self.shapes = shapes
        self.values = values
        self.constants = constants
        self.dicts: dict[str, Tracked] = {}
        # what `of` found each part named, by its identity
        self._names: dict[int, str | None] = {}
        self.named: Callable[[Expression], str] = lambda part: ""
        self.type_of: Callable[[Expression], type | None] = lambda part: None
        # whether the first ask holds each dict's other keys and makes none up
        self.keep = True
        # whether the ask keeps what each walk read at its place, and whether it held any
        self.pinned = True
        self.placed = False
        self.extra: dict[str, str] = {}
        self.functions: dict[str, str] = {}
        self.spent = 0
        self.stepped: set[tuple[str, str]] = set()
        self.most_lookups: int | None = None
        self.facts: dict[str, None] = {}
        # each value constant a dict declared, and what the answer names it by: a leaf's name,
        # or the dict and the key it is the value under
        self.valued: dict[str, tuple[str, object]] = {}

    @classmethod
    def of_path(
        cls, prefix: tuple[Branch, ...], origin: Origin, constants: Mapping[str, str]
    ) -> DictTerms:
        """The dicts of a path from the input whose path it is, with what the path asks of each
        noted, and the input's other keys held on the first ask."""
        terms = cls(origin.dicts, origin.values, constants)
        terms.keep = origin.keep
        terms.pinned = origin.pinned
        terms.most_lookups = origin.lookups
        terms.learn(prefix)
        return terms

    def of(self, part: Expression) -> Tracked | None:
        """The dict a part is, when the seed names one there. An access is written out as JSON
        to be looked up, so each part's name is worked out once."""
        name = part if isinstance(part, str) else access_name(part, self._names)
        if name is None or name not in self.shapes:
            return None
        if name not in self.dicts:
            symbol = f"dict.{list(self.shapes).index(name)}"
            self.dicts[name] = Tracked(name, symbol, self.shapes[name])
        return self.dicts[name]

    def learn(self, prefix: tuple[Branch, ...]) -> None:
        """Note what the path asks of each dict, in the order it asks: each part once, first to
        last, on a stack of its own, however deep or shared the parts are."""
        seen: set[int] = set()
        for fork in prefix:
            stack: list[Expression] = [fork.expression]
            while stack:
                part = stack.pop()
                if isinstance(part, list) and id(part) not in seen:
                    seen.add(id(part))
                    self._note(part)
                    stack.extend(reversed(part[1:]))
        for fork in prefix:
            holds = fork.holds
            if isinstance(holds, list) and holds[:1] == ["given"]:
                self._placed(holds[1], given=True)
            elif isinstance(holds, list):
                self._placed(holds)
        for found in self.dicts.values():
            found.asked = frozenset(found.named)
            if found.tracked:
                for key in found.shape.keys:
                    found.named.setdefault(key, len(found.named))

    def _placed(self, holds: Expression, *, given: bool = False) -> None:
        """Note which key a walk read at its place: ``["walked", A, k]`` from the first,
        ``["last", A, k]`` from the last, ``["exactly", A]`` at the target's own key; and when
        ``given``, that the place holds whatever a fork reads."""
        if not isinstance(holds, list) or len(holds) < 2:
            return
        head, part, *key = holds
        found = self.of(part)
        if found is None:
            return
        found.own = found.own or head == "exactly"
        literal = literal_key(key[0]) if key else MISSING
        if literal is not MISSING and literal in found.places:
            {"walked": found.walked, "last": found.last}.get(str(head), found.popped).add(literal)
            if given:
                found.given.add(literal)

    def _note(self, part: list[Expression]) -> None:
        head = part[0]
        if head == "in" and len(part) == 3 and (found := self.of(part[2])) is not None:
            self._key(found, part[1], held=False)
        elif head == "len" and len(part) == 2 and (found := self.of(part[1])) is not None:
            found.counted = True
        elif head == "[]" and len(part) == 3 and (found := self.of(part[1])) is not None:
            self._key(found, part[2], held=True)

    def _key(self, found: Tracked, key: Expression, *, held: bool) -> None:
        literal = literal_key(key)
        if literal is MISSING:
            found.tracked = True
            return
        found.named.setdefault(literal, len(found.named))
        if held:
            found.held.setdefault(literal)

    def involves(self, node: list[Expression]) -> bool:
        """Whether a part asks a dict about a key or its size."""
        head = node[0]
        if head == "in" and len(node) == 3:
            return self.of(node[2]) is not None
        return head in ("len", "[]") and len(node) >= 2 and self.of(node[1]) is not None

    def result(self, node: list[Expression]) -> type | None:
        """The type of what a dict part answers: whether a key is there, the size, or a value."""
        head = node[0]
        if head == "in":
            return bool
        if head == "len":
            return int
        found = self.of(node[1])
        assert found is not None
        return _VALUE_TYPES.get(self._value_kind(found, node[2]))

    def scalar(self, node: list[Expression]) -> str:
        """The term of a dict part: a key's presence, the size, or a value read."""
        head = node[0]
        found = self.of(node[2] if head == "in" else node[1])
        assert found is not None
        if head == "in":
            return self._presence(found, node[1])
        if head == "len":
            return found.constant("len")
        return self._read(found, node[1], node[2])

    def _presence(self, found: Tracked, key: Expression) -> str:
        literal = literal_key(key)
        if literal is not MISSING:
            return self.present(found, literal)
        return self.equals_a_key(found, self.named(key), self.type_of(key))

    def _value_kind(self, found: Tracked, key: Expression) -> str:
        """The kind of the value a read hands out: the kind under its key in the input, or of
        an added value; under a tracked key, the kind under the key it held in the input, or
        the one kind every value shares."""
        literal = literal_key(key)
        if literal is MISSING:
            held = self.values.get(leaf_name(key)) if isinstance(key, str | list) else None
            literal = held if held in found.places else MISSING
        if literal is not MISSING:
            return found.kind_under(literal)
        kinds = set(found.shape.kinds)
        return kinds.pop() if len(kinds) == 1 else "none"

    def _read(self, found: Tracked, container: Expression, key: Expression) -> str:
        """A value read under a key: a literal key's own value, which the dict holds; or under
        a tracked key, the value under whichever key it equals."""
        literal = literal_key(key)
        kind = self._value_kind(found, key)
        if kind not in _VALUE_TYPES:
            raise UnencodedError(f"pyct cannot render {key} in a dict: no int or str is read there")
        if literal is not MISSING:
            self.hold(self.present(found, literal))
            return self.value_under(found, container, literal, kind)
        term, typed = self.named(key), self.type_of(key)
        self.hold(self.equals_a_key(found, term, typed))
        return self.read_under(found, container, (term, typed), kind)

    def declarations(self) -> list[str]:
        """What the dicts declare: each size, each count, each key's presence, each value, and
        then each function a tracked key's lookup calls, which reads them."""
        lines: list[str] = []
        for found in self.dicts.values():
            lines += [
                f"(declare-const {found.constant(f'in.{j}')} Bool)" for j in range(len(found.named))
            ]
            if found.sized:
                lines += [f"(declare-const {found.constant(part)} Int)" for part in _COUNTS]
        lines += [f"(declare-const {name} {sort})" for name, sort in self.extra.items()]
        return lines + list(self.functions.values())

    def assertions(self) -> list[str]:
        """What the dicts assert: each size's equation and its bounds, the keys the path reads,
        and, on the first ask, the input's other keys kept and none made up."""
        lines: list[str] = []
        for found in self.dicts.values():
            lines += [f"(assert {self.present(found, key)})" for key in found.held]
            # a key of a type an answer cannot read back is one the solver does not add
            unread = [key for key in found.named if key not in found.places]
            unread = [key for key in unread if not found.shape.adds(key)]
            lines += [f"(assert (not {self.present(found, key)}))" for key in unread]
            if found.sized:
                lines += self._sized(found)
            lines += self._in_place(found)
        strings = [longest_string(name) for name, sort in self.extra.items() if sort == "String"]
        return lines + strings + list(self.facts)

    def _sized(self, found: Tracked) -> list[str]:
        size, kept, made = (found.constant(part) for part in _COUNTS)
        bits = [f"(ite {found.constant(f'in.{j}')} 1 0)" for j in range(len(found.named))]
        others = len(found.unnamed)
        lines = [
            f"(assert (= {size} (+ {' '.join([*bits, kept, made])})))",
            f"(assert (<= 0 {size} {MOST_ITEMS}))",
            f"(assert (<= 0 {kept} {others}))",
            f"(assert (<= 0 {made}))" if found.shape.makes_up else f"(assert (= {made} 0))",
        ]
        if self.keep:
            lines += [f"(assert (= {kept} {others}))", f"(assert (= {made} 0))"]
            unasked = [key for key in found.named if key in found.places and key not in found.asked]
            lines += [f"(assert {self.present(found, key)})" for key in unasked]
        return lines

    def _in_place(self, found: Tracked) -> list[str]:
        """What keeps each key a walk read at its place, where a fork reads the value under it:
        another key there would hand out another value, and that fork would read it instead.

        From the first, the input's keys stay up to the last walked key whose value a fork
        reads, and past the target's own key they all stay and none is added. From the last, a
        key read stays and none is added after it. A given place holds as a read one does.
        These hold on the asks that keep what a walk read (see ``pinned``) and on no other.
        """
        if not self.pinned:
            return []
        keep, closed = _held_in_place(found)
        named = dict.fromkeys(key for key in keep if key in found.named)
        lines = [f"(assert {self.present(found, key)})" for key in named]
        lines += _kept_past(found, keep)
        added = [
            f"(not {self.present(found, key)})" for key in found.named if key not in found.places
        ]
        if closed:
            lines += [f"(assert {fact})" for fact in added]
            lines += [f"(assert (= {found.constant('made')} 0))"] if found.sized else []
        lines += self._popped_unread(found, added)
        if lines:
            self.placed = True
        return lines

    def _popped_unread(self, found: Tracked, added: list[str]) -> list[str]:
        """What keeps popitem removing a key no fork names, where no fork reads what it
        returned: a made-up key last, or the key it read still last with none added. Another
        key a fork names, popped in its place, would change that fork."""
        unread = [key for key in found.popped if key not in found.held and key not in found.given]
        if not unread or not found.sized:
            return []
        facts = [_held_term(self, found, key) for key in unread]
        stays = f"(and true {' '.join([*facts, *added])})"
        return [f"(assert (or (> {found.constant('made')} 0) {stays}))"]

    @property
    def held_back(self) -> bool:
        """Whether the program holds a dict's other keys and makes none up: an unsat to it is
        asked again with both free."""
        return self.keep and any(found.sized for found in self.dicts.values())

    def asked(self) -> list[str]:
        """What the program asks cvc5 for about the dicts: every constant they declared."""
        names: list[str] = []
        for found in self.dicts.values():
            names += [found.constant(f"in.{j}") for j in range(len(found.named))]
            if found.sized:
                names += [found.constant(part) for part in _COUNTS]
        return names + list(self.extra)

    def answered(self) -> set[str]:
        """The names the answer holds for the dicts, as cvc5 writes them back: without bars."""
        return {name.strip("|") for name in self.asked()}


def _held_in_place(found: Tracked) -> tuple[list[object], bool]:
    """The input's keys that stay where a walk read them, and whether no key may be added: see
    ``DictTerms._in_place``."""
    places, read = found.places, {*found.held, *found.given}
    walked = [places[key] for key in found.walked if key in read]
    whole = found.own and bool(walked)
    through = len(places) - 1 if whole else max(walked, default=-1)
    last = [key for key in {*found.last, *found.popped} if key in read]
    keep = [key for key in places if places[key] <= through] + last
    return keep, whole or bool(last)


def _held_term(terms: Keyed, found: Tracked, key: object) -> str:
    """Whether the dict holds one of the input's keys: its `Bool`, or for a key no fork names,
    whether the count kept from the first reaches past it."""
    if key in found.named:
        return terms.present(found, key)
    return f"(< {found.unnamed.index(key)} {found.constant('kept')})"


def _kept_past(found: Tracked, keep: list[object]) -> list[str]:
    """How many of the input's keys no fork names stay, counted from the first: past every
    such key ``keep`` holds."""
    order = {key: at for at, key in enumerate(found.unnamed)}
    reach = max((order[key] + 1 for key in keep if key in order), default=0)
    if not reach or not found.sized:
        return []
    return [f"(assert (>= {found.constant('kept')} {reach}))"]


# the counts a dict with a size declares: its size, the input's other keys it keeps, and the
# keys pyct makes up
_COUNTS = ("len", "kept", "made")


__all__ = ["DictTerms", "Tracked", "TrackedDict", "made_up_match"]
