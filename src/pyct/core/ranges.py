"""The tracked range: a call written `range(...)` with a tracked int among its arguments.

Python does not let a class extend `range`, so a tracked range is a stand-in
that holds Python's own range, built from the plain values, for every answer,
and the arguments' forms for its forks (``README.md › Rules › forks``):

- Walking it, by a loop or by anything else that iterates, records one fork
  a pass saying the range has that element, and the pass after the last the
  same fork taken false. The fork compares the stop with the element, as
  Python's own loop does: ``[">", stop, element]`` for a positive step and
  ``["<", stop, element]`` for a negative one. The element at pass k is the
  start plus k times the step, with no node for adding 0 or multiplying by 1,
  and a plain int when it depends on no tracked value.
- A tracked step records ``["!=", step, 0]`` where the range is built, since
  Python raises ValueError on a zero step, and then ``[">", step, 0]``, whose
  side picks the compare the passes use.
- ``x in r`` is one fork, ``["in", x, ["range", start, stop]]``, with the step
  when the target passed one, whichever side is tracked.

Every other operation is range's own answer and a downgrade named by its
dunder, method or attribute (`values.downgrade_through`). `__hash__` and
`__repr__` stay range's.
"""

from __future__ import annotations

import operator
from collections.abc import Iterator
from typing import TypeGuard

from pyct.core import numbers
from pyct.core.bools import ConcolicBool
from pyct.core.branch import BranchSink, Downgrade, Expression
from pyct.core.ints import ConcolicInt
from pyct.core.list_reads import caller
from pyct.core.values import (
    copy_as_itself,
    downgrade_through,
    downgraded,
    forked,
    held_by,
    own,
)

# the most arguments range takes: a start, a stop and a step
_MOST = 3
# the tracked values range reads as ints
_TRACKED = (ConcolicInt, ConcolicBool)


def _form(value: object) -> Expression:
    """How a fork writes a bound: a tracked int by its expression, a plain one as the int."""
    if isinstance(value, _TRACKED):
        return value.expression
    return int.__index__(value)  # pyrefly: ignore[bad-argument-type]


def _plain(form: Expression) -> TypeGuard[int]:
    """Whether a form depends on no tracked value."""
    return type(form) is int


class ConcolicRange:
    """Python's range, held beside the forms of its start, stop and step, and a sink.

    `__iter__`, `__len__` for a walk's size, and `in` are taught below;
    every other method range has is its own answer on the held range and a
    downgrade, derived at the bottom of the module.
    """

    __slots__ = ("forms", "held", "sink", "walked_at", "written")

    def __init__(
        self,
        held: range,
        forms: tuple[Expression, Expression, Expression],
        written: int,
        sink: BranchSink,
    ) -> None:
        self.held = held
        self.forms = forms
        # the arguments the target passed, which an `in` fork writes as it passed them
        self.written = written
        self.sink = sink
        # the call that started the last walk, until its size is asked (see `_hinted`)
        self.walked_at: tuple[int, int] | None = None

    def __iter__(self) -> Iterator[object]:
        self.walked_at = caller(2)
        return _walked(self)

    def __len__(self) -> int:
        # Python's `len` makes the answer plain, so it is a downgrade, but for the size a walk
        # just started asks for, as `list(r)` asks it
        if not _hinted(self):
            self.sink.append(Downgrade(name="__len__"))
        return len(self.held)

    def __contains__(self, item: object) -> object:
        return contains(self, item)

    def __hash__(self) -> int:
        return hash(self.held)

    def __repr__(self) -> str:
        return repr(self.held)

    __copy__ = copy_as_itself
    __deepcopy__ = copy_as_itself

    @property
    def start(self) -> int:
        return _attribute(self, "start")

    @property
    def stop(self) -> int:
        return _attribute(self, "stop")

    @property
    def step(self) -> int:
        return _attribute(self, "step")


def _attribute(r: ConcolicRange, name: str) -> int:
    """An attribute of range, read plain: range's own value and a downgrade named by it."""
    r.sink.append(Downgrade(name=name))
    return getattr(r.held, name)


def _hinted(r: ConcolicRange) -> bool:
    """Whether a `__len__` call is Python's own guess at the size of a walk it just started.

    `list(r)`, `tuple(r)` and `sorted(r)` start a walk and then ask the
    length in the same call of the same code. Only the first ask after a
    walk starts can be that guess.
    """
    started, r.walked_at = r.walked_at, None
    # this function, then the range's `__len__`, then the code that asked
    return started is not None and started == caller(3)


def ranged(*args: object, **kwargs: object) -> object:
    """A tracked range from the arguments of a call written `range(...)`.

    Python reads each argument as an int by `__index__` and refuses what it
    cannot read, before it looks at the step; a tracked step then records its
    two forks, and a zero step raises Python's own ValueError.
    """
    if kwargs or not 1 <= len(args) <= _MOST:
        return own(range, *args, **kwargs)
    # Python's own index makes a tracked int plain, and a tracked one is an int already
    indexed = [arg if isinstance(arg, _TRACKED) else own(operator.index, arg) for arg in args]
    bounds = [0, indexed[0], 1] if len(indexed) == 1 else [*indexed, 1][:_MOST]
    step = bounds[2]
    if isinstance(step, _TRACKED):
        _signed(step)
    held = own(range, *indexed)
    sink = next((arg.sink for arg in indexed if isinstance(arg, _TRACKED)), None)
    if sink is None:
        return held
    start, stop, step_form = (_form(bound) for bound in bounds)
    return ConcolicRange(held, (start, stop, step_form), len(indexed), sink)


def _signed(step: ConcolicInt | ConcolicBool) -> None:
    """The forks a tracked step records: not zero, which Python raises on, and then its sign."""
    value = int.__index__(step)
    if forked(step.sink, ["!=", step.expression, 0], value != 0):
        forked(step.sink, [">", step.expression, 0], value > 0)


def _element(r: ConcolicRange, at: int) -> Expression:
    """The form of the element at pass ``at``: the start plus ``at`` times the step."""
    start, _, step = r.forms
    if _plain(step):
        scaled: Expression = at * step
    else:
        scaled = 0 if at == 0 else step if at == 1 else ["*", at, step]
    if _plain(start) and _plain(scaled):
        return start + scaled
    if _plain(start) and start == 0:
        return scaled
    return start if scaled == 0 and _plain(scaled) else ["+", start, scaled]


def _passed(r: ConcolicRange, element: Expression, taken: bool) -> None:
    """Record a pass's fork, the stop against the element, unless neither depends on anything."""
    stop = r.forms[1]
    if not (_plain(stop) and _plain(element)):
        compare = ">" if r.held.step > 0 else "<"
        forked(r.sink, [compare, stop, element], taken, "__iter__")


def _walked(r: ConcolicRange) -> Iterator[object]:
    """Each element of the held range, one fork a pass and one where the walk ends."""
    at = 0
    for value in r.held:
        element = _element(r, at)
        _passed(r, element, True)
        yield value if _plain(element) else numbers.tracked(value, element, r.sink)
        at += 1
    _passed(r, _element(r, at), False)


def _spelled(r: ConcolicRange) -> Expression:
    """The range as an `in` fork writes it: its arguments as the target passed them."""
    start, stop, step = r.forms
    return ["range", start, stop, step] if r.written == _MOST else ["range", start, stop]


def range_form(r: range) -> Expression:
    """A plain range as an `in` fork writes it: its start and stop, and a step other than 1."""
    form: list[Expression] = ["range", r.start, r.stop]
    return form if r.step == 1 else [*form, r.step]


# the ints an `in` fork takes as its item: a plain one as the int, a tracked one by its form
_INTS = (int, bool, ConcolicInt, ConcolicBool)


def contains(r: ConcolicRange, item: object) -> object:
    """``item in r`` for a tracked range: its answer with the condition, untested.

    An item that is not an int is range's own answer and a downgrade.
    """
    if type(item) not in _INTS:
        return _CONTAINS_DOWNGRADE(r, item)
    answer = own(range.__contains__, r.held, _value(item))
    return ConcolicBool(answer, expression=["in", _item(item), _spelled(r)], sink=r.sink)


def not_contains(r: ConcolicRange, item: object) -> object:
    """``item not in r`` for a tracked range, as `contains` answers it, with `not in` its head."""
    if type(item) not in _INTS:
        return not _CONTAINS_DOWNGRADE(r, item)
    answer = not own(range.__contains__, r.held, _value(item))
    return ConcolicBool(answer, expression=["not in", _item(item), _spelled(r)], sink=r.sink)


def within(item: ConcolicInt | ConcolicBool, r: range) -> ConcolicBool:
    """``item in r`` for a tracked int and a plain range: one fork, where Python alone would
    compare the item with every element in turn."""
    answer = r.__contains__(_value(item))
    return ConcolicBool(answer, expression=["in", item.expression, range_form(r)], sink=item.sink)


def not_within(item: ConcolicInt | ConcolicBool, r: range) -> ConcolicBool:
    """``item not in r`` for a tracked int and a plain range, as `within` answers it."""
    answer = not r.__contains__(_value(item))
    return ConcolicBool(
        answer, expression=["not in", item.expression, range_form(r)], sink=item.sink
    )


def _value(item: object) -> int:
    """An int item's plain value, which range answers without walking its elements."""
    return int.__index__(item)  # pyrefly: ignore[bad-argument-type]


def _item(item: object) -> Expression:
    """How an `in` fork writes its item: a tracked one's expression, a plain int as itself."""
    return item.expression if isinstance(item, _TRACKED) else item  # pyrefly: ignore[bad-return]


# the class body above is everything ConcolicRange teaches; the rest of range is derived here,
# range's own answer on the held range and a downgrade
downgrade_through(ConcolicRange, range, kept=("__getattribute__",))
# `in` with an item that is not an int, which range answers by comparing it with each element
_CONTAINS_DOWNGRADE = downgraded(range, "__contains__", calling=held_by(range.__contains__))
