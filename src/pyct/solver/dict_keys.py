"""How a dict's keys are written for cvc5: a key a fork names, and a tracked key that names none.

A literal key a fork names is its own `Bool`. A tracked key equals a key the dict holds when it
equals one the input holds, still kept, one the path names, held, or one pyct makes up: `pyct`
and a number n, written as `str.from_int` writes it, not a text the dict holds or a fork names,
and among the first ``made`` such texts; under ``dict[int, X]``, a non-negative int the dict
does not hold and no fork names, among the first ``made`` such ints (dict-keys-named-held-made-
up-or-changed-under-a-tracked-key). A value read under a tracked key is the value under the key
it equals; under a made-up key, one value declared for them all.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import TYPE_CHECKING

from pyct.binding.bind import leaf_name
from pyct.binding.shapes import MADE_UP
from pyct.core.branch import Expression
from pyct.solver.heads import SORTS
from pyct.solver.list_reader import ProgramTooLargeError
from pyct.solver.literals import is_literal, leaf_term, value
from pyct.solver.strings import encode

if TYPE_CHECKING:
    from pyct.solver.dicts import Tracked

# a key a fork does not name as a literal, and the value under a made-up key: apart from every key
MISSING = object()
MADE = object()

# the type a value of each kind is read as
_TYPES: dict[str, type] = {"int": int, "str": str}

# whether an int term equals one of n int keys costs cvc5 time that grows with the square of n:
# one tracked int key looked up took 0.07 s in 200 keys, 1.05 s in 1,000 and 9.7 s in 3,000,
# and reading the value under it added a tenth or less, against 0.03 s, 0.14 s and 0.50 s for a
# str key looked up and read (cvc5 1.3.4, macOS arm64, load 2 to 5). So an int key's lookup
# into n keys counts (n + 1) squared over this many steps, and never fewer than a str key's:
# into 3,000 keys 375,000 steps, past the 350,000 the 10 s default allows, and into 1,000 keys
# 41,800, asked
INT_KEY_STEPS = 24


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


def made_up_int_match(term: str, taken: Collection[object], made: str) -> str:
    """Whether an int term equals one of the first ``made`` made-up int keys: a non-negative
    int not in ``taken``, with fewer than ``made`` such ints below it."""
    skipped = sorted({key for key in taken if type(key) is int and key >= 0})
    before = " ".join(f"(ite (< {leaf_term(n)} {term}) 1 0)" for n in skipped)
    apart = " ".join(f"(not (= {term} {leaf_term(n)}))" for n in skipped)
    return f"(and (>= {term} 0) {apart} (< (- {term} (+ 0 0 {before})) {made}))"


def call_steps(keys: int, typed: type | None) -> int:
    """The steps a tracked key's lookup counts, into a dict with ``keys`` keys of the key's
    type: a str key's grow with the keys, an int key's with their square (see
    ``INT_KEY_STEPS``)."""
    steps = keys + 1
    return max(steps, steps * steps // INT_KEY_STEPS) if typed is int else steps


class LookupsTooManyError(ProgramTooLargeError):
    """A path's tracked-key lookups ran past the steps the solve's limit gives them."""


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
    # each function a tracked key's lookup or read calls, by name, as the program defines it
    functions: dict[str, str]
    # the steps the program's tracked-key lookups have taken, each call they counted, and the
    # most they may take, None for no limit: cvc5 writes each call out over every key the
    # function reads
    spent: int
    stepped: set[tuple[str, str]]
    most_lookups: int | None

    def _step(self, found: Tracked, keyed: tuple[type | None, str], *functions: str) -> None:
        """Count the calls of a tracked key's read, each as many steps as the keys it may equal
        and one more, as cvc5 writes each call out; its lookup's call counts as ``call_steps``
        says. A call the program already makes, as a loop's lookup of one key on each pass,
        counts once: cvc5 shares the term. A program past its steps is given up before cvc5
        grows it out of reach. ``keyed`` is the key's type and its term."""
        typed, term = keyed
        fresh = {(function, term) for function in functions} - self.stepped
        self.stepped |= fresh
        keys = len(found.candidates(typed))
        has = found.constant(f"has.{_sort_word(typed)}")
        lookups = sum(function == has for function, _ in fresh)
        self.spend(lookups * call_steps(keys, typed) + (len(fresh) - lookups) * (keys + 1))

    def spend(self, steps: int) -> None:
        """Count steps of the program's tracked-key lookups, and give the program up past the
        most it may take."""
        self.spent += steps
        if self.most_lookups is not None and self.spent > self.most_lookups:
            raise LookupsTooManyError(
                f"tracked-key lookups ran past {self.most_lookups} steps into the dict's keys"
            )

    def hold(self, fact: str) -> None:
        """Assert, once, a fact every input on the path meets."""
        self.facts.setdefault(f"(assert {fact})")

    def present(self, found: Tracked, key: object) -> str:
        """Whether the dict holds a key the path names: its `Bool`."""
        return found.constant(f"in.{found.named[key]}")

    def _equals(self, found: Tracked, key: object) -> str:
        """Whether the function's argument ``k`` equals a key the dict holds: every key a
        tracked key may equal is named, the input's among them (see ``DictTerms.learn``)."""
        return f"(and (= k {key_term(key)}) {self.present(found, key)})"

    def _function(self, name: str, typed: type | None, result: str, body: str) -> str:
        """A function of one key of that type, defined once, and its name."""
        if name not in self.functions:
            sort = SORTS.get(typed, "Int") if typed is not None else "Int"
            self.functions[name] = f"(define-fun {name} ((k {sort})) {result} {body})"
        return name

    def equals_a_key(self, found: Tracked, term: str, typed: type | None) -> str:
        """Whether a tracked key equals a key the dict holds, a made-up one among them.

        The keys are written once, in a function each lookup calls, so a path's program grows
        with its keys and its lookups, not with the one times the other.
        """
        name = found.constant(f"has.{_sort_word(typed)}")
        self._step(found, (typed, term), name)
        if name not in self.functions:
            options = [self._equals(found, key) for key in found.candidates(typed)]
            if typed is found.shape.made_type and found.shape.makes_up:
                taken = {*found.shape.keys, *found.named}
                match = made_up_int_match if typed is int else made_up_match
                options.append(match("k", taken, found.constant("made")))
            self._function(name, typed, "Bool", f"(or false {' '.join(options)})")
        return f"({name} {term})"

    def read_under(
        self, found: Tracked, container: Expression, keyed: tuple[str, type | None], kind: str
    ) -> str:
        """The value under whichever key a tracked key equals, of the kind the read hands out.

        A key whose value is of another kind is one the tracked key does not equal on this
        path; a made-up key holds the one value declared for made-up keys. Both are written
        once, as functions each read calls.
        """
        term, typed = keyed
        word = f"{_sort_word(typed)}.{kind}"
        # a read calls two functions: whether the key's value is of the kind read, and the value
        fits, read = found.constant(f"fits.{word}"), found.constant(f"read.{word}")
        self._step(found, (typed, term), fits, read)
        if read not in self.functions:
            body = self._declared(found, f"made.{kind}", kind, (found.name, MADE))
            others: list[str] = []
            for key in reversed(found.candidates(typed)):
                if found.kind_under(key) != kind:
                    others.append(f"(not {self._equals(found, key)})")
                    continue
                value = self.value_under(found, container, key, kind)
                body = f"(ite {self._equals(found, key)} {value} {body})"
            self._function(fits, typed, "Bool", f"(and true {' '.join(others)})")
            self._function(read, typed, SORTS[_TYPES[kind]], body)
        self.hold(f"({fits} {term})")
        return f"({read} {term})"

    def value_under(self, found: Tracked, container: Expression, key: object, kind: str) -> str:
        """The value under a key: the input's own value's constant, when the path names it, or
        one declared here, which the answer names by the input's leaf or as an added value."""
        access: Expression = ["[]", container, key_term(key, written=True)]
        held = key in found.places
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


def _sort_word(typed: type | None) -> str:
    """The word a function's name carries for the type of key it takes."""
    return "str" if typed is str else "int"
