"""A dict's walk in the ask with chosen keys, written for cvc5 (let-the-solver-choose-a-small-
dict-s-walk-key).

Each pass up to the last one the path names holds a key the dict holds: a chosen key, a leaf
that equals one of the input's keys, one a fork names or one pyct makes up, as a tracked key
does (``dict_keys``); or the input's key there. The keys differ from each other, and the answer
lists them first, in pass order (``binding.shapes.rekeyed``), so Python's walk of it reads each
at its pass. A literal the path compares a chosen key with by `==` or `!=` is a key a fork
names, which the solver may add.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from pyct.core.branch import Expression
from pyct.solver.dict_keys import MISSING, call_steps, key_term, literal_key

if TYPE_CHECKING:
    from pyct.solver.dicts import DictTerms, Tracked

# the compares whose literal is a key a fork names
_COMPARES = ("==", "!=")

# the heads of the places that hold a dict to the size a walk handing out walk keys takes, and
# its walk in its order
CAPPED, ORDER = "capped", "order"


def capped(name: str) -> Expression:
    """The place that holds a dict whose walk handed out walk keys to the size such a walk
    takes."""
    return [CAPPED, name]


def order(name: str, passes: tuple[tuple[str | None, object], ...]) -> Expression:
    """The place that holds a dict's walk in its order: each pass's chosen leaf, or None, and
    the input's key there."""
    written: list[Expression] = [ORDER, name]
    for chosen, key in passes:
        assert type(key) is str or type(key) is int
        written.append([chosen, key])
    return written


def ordered(terms: DictTerms, places: tuple[Expression, ...]) -> tuple[Expression, ...]:
    """Note each dict's cap and order, and hand back the other places. A dict with an order is
    read by tracked keys, and holds each input key the order keeps."""
    others: list[Expression] = []
    for place in places:
        if not (isinstance(place, list) and len(place) >= 2 and place[0] in (CAPPED, ORDER)):
            others.append(place)
            continue
        found = terms.of(place[1])
        if found is None:
            continue
        found.capped = True
        if place[0] == ORDER:
            _order(terms, found, place[2:])
    return tuple(others)


def _order(terms: DictTerms, found: Tracked, passes: list[Expression]) -> None:
    order: list[tuple[str | None, object]] = []
    for written in passes:
        assert isinstance(written, list) and len(written) == 2
        chosen, key = written
        assert chosen is None or isinstance(chosen, str)
        order.append((chosen, key))
        if chosen is not None:
            terms.walk_leaves[chosen] = found.name
        else:
            found.named.setdefault(key, len(found.named))
            found.held.setdefault(key)
    found.order = tuple(order)
    found.tracked = True


def compared(terms: DictTerms, part: list[Expression]) -> None:
    """Name the literal a chosen key is compared with by `==` or `!=` in that key's dict."""
    if part[0] not in _COMPARES or len(part) != 3:
        return
    for chosen, other in ((part[1], part[2]), (part[2], part[1])):
        name = terms.walk_leaves.get(chosen) if isinstance(chosen, str) else None
        literal = literal_key(other)
        found = None if name is None else terms.of(name)
        if found is not None and literal is not MISSING and type(literal) is found.key_type:
            found.named.setdefault(literal, len(found.named))


def order_lines(terms: DictTerms, found: Tracked) -> list[str]:
    """What holds a dict's order: each chosen key equals a key the dict holds, and the keys of
    the order differ. Each pair of chosen keys counts as a lookup does (see ``Keyed.spend``):
    200 int keys took 0.20 s with 3 chosen, 0.59 s with 5 and 1.5 s with 10, each looked up and
    read (cvc5 1.3.4, macOS arm64, load 1 to 8)."""
    typed = found.key_type
    written: list[str] = []
    for chosen, key in found.order:
        constant = None if chosen is None else terms.constants.get(chosen)
        if constant is None:
            written.append(str(key_term(key)))
            continue
        terms.hold(terms.equals_a_key(found, constant, typed))
        written.append(constant)
    count = sum(chosen is not None for chosen, _ in found.order)
    terms.spend(count * (count - 1) // 2 * call_steps(len(found.candidates(typed)), typed))
    return [f"(assert (distinct {' '.join(written)}))"] if len(written) > 1 else []


def first_keys(terms: DictTerms, found: Tracked, model: Mapping[str, object]) -> tuple[object, ...]:
    """The keys an answer lists first: each pass's chosen key, as the model says, or the
    input's key there."""
    keys: list[object] = []
    for chosen, key in found.order:
        constant = None if chosen is None else terms.constants.get(chosen)
        keys.append(key if constant is None else model[constant.strip("|")])
    return tuple(keys)
