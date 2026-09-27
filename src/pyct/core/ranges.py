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

- ``r == other`` with another range, tracked or plain, is its answer with
  one condition, ``["==", ["range", ...], ["range", ...]]``, untested, and
  ``!=`` the same with its own head.
- ``start``, ``stop`` and ``step`` are the arguments the target passed, a
  tracked one as itself (downgrades-class-body-taught-attributes-named).

Every other operation is range's own answer and a downgrade named by its
dunder or method (`values.downgrade_through`); a pickle holds Python's range
and records `__reduce_ex__` (pickle-holds-the-plain-value). `__hash__` and
`__repr__` stay range's. A tracked range is a `Sequence`, as Python's is, so
`random.sample` and `match` read it as one. It reports range as its class,
so `isinstance(r, range)` holds as for Python's own, and pyct tells it apart
by `type(r)` (tracked-values-report-their-base-type-as-their-class).
"""

from __future__ import annotations

import operator
from collections.abc import Iterator, Sequence
from typing import Any, Self, SupportsIndex, TypeGuard

from pyct.core import numbers
from pyct.core.bools import ConcolicBool
from pyct.core.branch import BranchSink, Downgrade, Expression
from pyct.core.ints import ConcolicInt
from pyct.core.list_reads import caller, hinted
from pyct.core.values import (
    REPORTED_CLASS,
    as_base,
    copy_as_itself,
    downgrade_through,
    downgraded,
    forked,
    held_by,
    own,
)

# the most arguments range takes: a start, a stop and a step
_MOST = 3
# the tracked values range reads as ints, and an `in` searches a range for with one fork
TRACKED_INTS = (ConcolicInt, ConcolicBool)


def _form(value: object) -> Expression:
    """How a fork writes a bound: a tracked int by its expression, a plain one as the int."""
    if isinstance(value, TRACKED_INTS):
        return value.expression
    return int.__index__(value)  # pyrefly: ignore[bad-argument-type]


def _plain(form: Expression) -> TypeGuard[int]:
    """Whether a form depends on no tracked value."""
    return type(form) is int


class ConcolicRange:
    """Python's range, held beside the forms of its start, stop and step, and a sink.

    `__iter__`, `__len__` for a walk's size, `in`, `==`, `!=` and the
    three attributes are taught below; every other method range has is its
    own answer on the held range and a downgrade, derived at the bottom of
    the module.
    """

    __slots__ = ("bounds", "forms", "held", "sink", "walked_at", "written")

    # the base type, as `isinstance`, singledispatch and a class pattern read it; the class
    # called with a value is range's own, a plain range, and pyct builds a tracked one by `made`
    __class__ = REPORTED_CLASS  # pyrefly: ignore[bad-override]
    __new__ = as_base

    held: range
    # the start, the stop and the step, a tracked one as the target passed it, and each's form
    bounds: tuple[int, int, int]
    forms: tuple[Expression, Expression, Expression]
    # how many arguments the target passed, which an `in` or `==` fork writes as passed
    written: int
    sink: BranchSink
    # the call that started the last walk, until its size is asked (see `list_reads.hinted`)
    walked_at: tuple[int, int] | None

    @classmethod
    def made(
        cls, held: range, bounds: tuple[int, int, int], written: int, sink: BranchSink
    ) -> Self:
        """A tracked range holding Python's own, beside its bounds' forms: how pyct builds one."""
        made = object.__new__(cls)
        made.held = held
        made.bounds = bounds
        made.forms = (_form(bounds[0]), _form(bounds[1]), _form(bounds[2]))
        made.written = written
        made.sink = sink
        made.walked_at = None
        return made

    def __iter__(self) -> Iterator[object]:
        self.walked_at = caller(2)
        return _walked(self)

    def __len__(self) -> int:
        # Python's `len` makes the answer plain, so it is a downgrade, but for the size a walk
        # just started asks for, as `list(r)` asks it
        if not hinted(self):
            self.sink.append(Downgrade(name="__len__"))
        # past the largest size Python raises OverflowError, the target's as in plain Python
        return own(len, self.held)

    def __contains__(self, item: object) -> object:
        return contains(self, item)

    def __hash__(self) -> int:
        return hash(self.held)

    def __repr__(self) -> str:
        return repr(self.held)

    def __eq__(self, other: object) -> object:  # pyrefly: ignore[bad-override]
        return _compared(self, other, "==")

    def __ne__(self, other: object) -> object:  # pyrefly: ignore[bad-override]
        return _compared(self, other, "!=")

    def __reduce_ex__(self, protocol: SupportsIndex, /) -> str | tuple[Any, ...]:
        # a pickle holds Python's range, and writing it is a downgrade at every protocol
        self.sink.append(Downgrade(name="__reduce_ex__"))
        return own(self.held.__reduce_ex__, protocol)

    __copy__ = copy_as_itself
    __deepcopy__ = copy_as_itself

    @property
    def start(self) -> int:
        return self.bounds[0]

    @property
    def stop(self) -> int:
        return self.bounds[1]

    @property
    def step(self) -> int:
        return self.bounds[2]


def _compared(r: ConcolicRange, other: object, op: str) -> object:
    """``r == other`` or ``r != other``: range's answer with its condition, untested, when the
    other is a range too, and NotImplemented otherwise, as range's own gives."""
    if type(other) is ConcolicRange:
        held, form = other.held, _spelled(other)
    elif type(other) is range:
        held, form = other, range_form(other)
    else:
        return NotImplemented
    same = own(range.__eq__, r.held, held)
    answer = same if op == "==" else not same
    return ConcolicBool.made(answer, expression=[op, _spelled(r), form], sink=r.sink)


def ranged(*args: object, **kwargs: object) -> object:
    """A tracked range from the arguments of a call written `range(...)`.

    Python reads each argument as an int by `__index__` and refuses what it
    cannot read, before it looks at the step; a tracked step then records its
    two forks, and a zero step raises Python's own ValueError.
    """
    if kwargs or not 1 <= len(args) <= _MOST:
        return own(range, *args, **kwargs)
    indexed = [_index(arg) for arg in args]
    bounds = [0, indexed[0], 1] if len(indexed) == 1 else [*indexed, 1][:_MOST]
    step = bounds[2]
    if isinstance(step, TRACKED_INTS):
        _signed(step)
    held = own(range, *indexed)
    sink = next((arg.sink for arg in indexed if isinstance(arg, TRACKED_INTS)), None)
    if sink is None:
        return held
    return ConcolicRange.made(held, (bounds[0], bounds[1], bounds[2]), len(indexed), sink)


def _index(arg: object) -> int:
    """An argument as range reads it, by `__index__`: a tracked one as the tracked int it is.

    Python's own index would make a tracked int plain, so a tracked one is
    asked its own `__index__`, which hands a tracked bool back as a tracked int.
    """
    if isinstance(arg, TRACKED_INTS):
        return arg.__index__()
    return own(operator.index, arg)


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
    return ConcolicBool.made(answer, expression=["in", _item(item), _spelled(r)], sink=r.sink)


def not_contains(r: ConcolicRange, item: object) -> object:
    """``item not in r`` for a tracked range, as `contains` answers it, with `not in` its head."""
    if type(item) not in _INTS:
        return not _CONTAINS_DOWNGRADE(r, item)
    answer = not own(range.__contains__, r.held, _value(item))
    return ConcolicBool.made(answer, expression=["not in", _item(item), _spelled(r)], sink=r.sink)


def within(item: ConcolicInt | ConcolicBool, r: range) -> ConcolicBool:
    """``item in r`` for a tracked int and a plain range: one fork, where Python alone would
    compare the item with every element in turn."""
    answer = r.__contains__(_value(item))
    return ConcolicBool.made(
        answer, expression=["in", item.expression, range_form(r)], sink=item.sink
    )


def not_within(item: ConcolicInt | ConcolicBool, r: range) -> ConcolicBool:
    """``item not in r`` for a tracked int and a plain range, as `within` answers it."""
    answer = not r.__contains__(_value(item))
    return ConcolicBool.made(
        answer, expression=["not in", item.expression, range_form(r)], sink=item.sink
    )


def _value(item: object) -> int:
    """An int item's plain value, which range answers without walking its elements."""
    return int.__index__(item)  # pyrefly: ignore[bad-argument-type]


def _item(item: object) -> Expression:
    """How an `in` fork writes its item: a tracked one's expression, a plain int as itself."""
    return item.expression if isinstance(item, TRACKED_INTS) else item  # pyrefly: ignore[bad-return]


# the class body above is everything ConcolicRange teaches; the rest of range is derived here,
# range's own answer on the held range and a downgrade
downgrade_through(ConcolicRange, range, kept=("__getattribute__",))
# `in` with an item that is not an int, which range answers by comparing it with each element
_CONTAINS_DOWNGRADE = downgraded(range, "__contains__", calling=held_by(range.__contains__))
# a sequence, as Python's range is: `random.sample` asks the ABC, and `match` the flag it sets
Sequence.register(ConcolicRange)  # pyrefly: ignore[missing-attribute]
