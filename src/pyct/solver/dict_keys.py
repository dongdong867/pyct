"""How a dict's keys are written for cvc5: a key a fork names, and a tracked key that names none.

A literal key a fork names is its own `Bool`. A tracked key equals a key the dict holds when it
equals one the input holds, still kept, one the path names, held, or one pyct makes up: `pyct`
and a number n, written as `str.from_int` writes it, not a text the dict holds or a fork names,
and among the first ``made`` such texts (dict-keys-named-held-or-made-up). A value read under a
tracked key is the value under the key it equals; under a made-up key, one value declared for
them all.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import TYPE_CHECKING

from pyct.binding.bind import leaf_name
from pyct.binding.shapes import MADE_UP
from pyct.core.branch import Expression
from pyct.solver.heads import SORTS
from pyct.solver.literals import is_literal, leaf_term, value
from pyct.solver.strings import encode

if TYPE_CHECKING:
    from pyct.solver.dicts import Tracked

# a key a fork does not name as a literal, and the value under a made-up key: apart from every key
MISSING = object()
MADE = object()

# the type a value of each kind is read as
_TYPES: dict[str, type] = {"int": int, "str": str}


def literal_key(key: Expression) -> object:
    """The key a fork names as a literal, a str in its quotes or an int, or MISSING for a key
    the fork writes by its expression, a tracked one."""
    if isinstance(key, str) and is_literal(key):
        return value(key)
    if type(key) is int:
        return key
    return MISSING


def key_term(key: object, *, written: bool = False) -> Expression:
    """A key as a fork writes it, or with ``written`` false as cvc5 reads it."""
    if isinstance(key, str):
        return str.__repr__(key) if written else encode(key)
    assert type(key) is int
    return key if written else leaf_term(key)


def made_up_number(text: object) -> int | None:
    """The number of a text a made-up key could be, `pyct3` say, or None for any other."""
    if not isinstance(text, str) or not text.startswith(MADE_UP):
        return None
    digits = text[len(MADE_UP) :]
    if not digits.isascii() or not digits.isdigit() or digits.startswith("0"):
        return None
    return int(digits)


def made_up_match(term: str, taken: Collection[object], made: str) -> str:
    """Whether a str term equals one of the first ``made`` made-up keys, skipping ``taken``."""
    start = len(MADE_UP)
    suffix = f"(str.substr {term} {start} (- (str.len {term}) {start}))"
    number = f"(str.to_int {suffix})"
    skipped = sorted(n for key in taken if (n := made_up_number(key)) is not None)
    before = " ".join(f"(ite (< {n} {number}) 1 0)" for n in skipped)
    apart = " ".join(f"(not (= {number} {n}))" for n in skipped)
    return (
        f"(and (str.prefixof {encode(MADE_UP)} {term}) (>= {number} 1) "
        f"(= {suffix} (str.from_int {number})) {apart} (<= (- {number} (+ 0 0 {before})) {made}))"
    )


class Keyed:
    """The terms of a dict's keys and of the values under them: mixed into ``DictTerms``, which
    sets what they read.

    ``constants`` holds the constant of each leaf the path names. ``extra`` holds each
    constant a dict declared, with its sort; ``valued`` what the answer names each value
    constant by: a leaf's name, or the dict and the key it is the value under.
    """

    constants: Mapping[str, str]
    extra: dict[str, str]
    valued: dict[str, tuple[str, object]]
    facts: dict[str, None]

    def hold(self, fact: str) -> None:
        """Assert, once, a fact every input on the path meets."""
        self.facts.setdefault(f"(assert {fact})")

    def present(self, found: Tracked, key: object) -> str:
        """Whether the dict holds a key the path names: its `Bool`."""
        return found.constant(f"in.{list(found.named).index(key)}")

    def _held(self, found: Tracked, key: object) -> str:
        """Whether the dict holds a key of the input or of the path: a named key's `Bool`, and
        for the input's other keys, whether the count kept reaches its place."""
        if key in found.named:
            return self.present(found, key)
        return f"(< {found.unnamed.index(key)} {found.constant('kept')})"

    def kind_under(self, found: Tracked, key: object) -> str:
        """The kind of the value under a key: the input's, or an added value's."""
        if key in found.shape.keys:
            return found.shape.kinds[found.shape.keys.index(key)]
        return found.shape.fill

    def _equals(self, found: Tracked, term: str, key: object) -> str:
        return f"(and (= {term} {key_term(key)}) {self._held(found, key)})"

    def equals_a_key(self, found: Tracked, term: str, typed: type | None) -> str:
        """Whether a tracked key equals a key the dict holds, a made-up one among them."""
        options = [self._equals(found, term, key) for key in found.candidates(typed)]
        if typed is str and found.shape.makes_up:
            taken = {*found.shape.keys, *found.named}
            options.append(made_up_match(term, taken, found.constant("made")))
        return f"(or false {' '.join(options)})"

    def read_under(
        self, found: Tracked, container: Expression, keyed: tuple[str, type | None], kind: str
    ) -> str:
        """The value under whichever key a tracked key equals, of the kind the read hands out.

        A key whose value is of another kind is one the tracked key does not equal on this
        path; a made-up key holds the one value declared for made-up keys.
        """
        term, typed = keyed
        read = self._declared(found, f"made.{kind}", kind, (found.name, MADE))
        for key in reversed(found.candidates(typed)):
            here = self._equals(found, term, key)
            if self.kind_under(found, key) != kind:
                self.hold(f"(not {here})")
                continue
            read = f"(ite {here} {self.value_under(found, container, key, kind)} {read})"
        return read

    def value_under(self, found: Tracked, container: Expression, key: object, kind: str) -> str:
        """The value under a key: the input's own value's constant, when the path names it, or
        one declared here, which the answer names by the input's leaf or as an added value."""
        access: Expression = ["[]", container, key_term(key, written=True)]
        held = key in found.shape.keys
        constant = self.constants.get(leaf_name(access)) if held else None
        if constant is not None:
            return constant
        answer = (leaf_name(access), MISSING) if held else (found.name, key)
        return self._declared(found, f"v.{found.slot(key)}", kind, answer)

    def _declared(self, found: Tracked, part: str, kind: str, answer: tuple[str, object]) -> str:
        name = found.constant(part)
        if name not in self.extra:
            self.extra[name] = SORTS[_TYPES[kind]]
            self.valued[name] = answer
        return name
