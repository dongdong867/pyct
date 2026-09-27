"""The concolic str: a real str that also carries its symbolic form."""

from __future__ import annotations

from collections.abc import Callable

from pyct.core.bools import ConcolicBool
from pyct.core.branch import BranchSink, Expression
from pyct.core.ints import ConcolicInt
from pyct.core.numbers import compare
from pyct.core.values import copy_as_itself, downgrade_the_rest, downgraded, forked, own, pickled

# the `ConcolicStr` body below is the taught set: the compares, the truth test, the searches and
# the pieces it writes stay symbolic, and a copy is the value itself. The tuple here names what
# is left to str on purpose, and the derivation at the bottom of the file downgrades every other
# method str defines, plain methods and operators alike. str defines `__str__` and `__format__`
# itself, so nothing inherited needs naming.

# not the target's path: `__hash__`, `__repr__`, `__getnewargs__` and the rest of the object
# plumbing, so a dict key and a debugger read cost nothing. str takes `__getattribute__` from
# object today; it is kept all the same, because the downgrade wrapper reads `self.sink`
# through it, and a wrapped one would recurse on the first attribute read
_KEPT = (
    "__hash__",
    "__repr__",
    "__getnewargs__",
    "__new__",
    "__getattribute__",
    "__sizeof__",
)

# the last character cvc5 holds: its strings run from U+0000 to here, and the solver writes
# every one of them
LAST_CHARACTER = 0x2FFFF


def _operand(other: object) -> Expression | None:
    """The symbolic form of an operand str takes, or None for one it does not.

    A tracked str gives its expression. Any other str is a literal of its
    plain value, written as repr writes it, so a literal keeps its quotes and
    reads apart from a parameter name.
    """
    if isinstance(other, ConcolicStr):
        return other.expression
    if isinstance(other, str):
        # str's own repr: a str of the target's own may print itself another way
        return str.__repr__(other)
    return None


def _within_cvc5(other: object) -> bool:
    """Whether the solver reads the other side of a compare as it is.

    A tracked str is read by its expression, and a non-str is Python's own
    business, so only a plain str's characters are checked, each against the
    last one cvc5 holds.
    """
    if isinstance(other, ConcolicStr) or not isinstance(other, str):
        return True
    return all(ord(character) <= LAST_CHARACTER for character in other)


def _compare(op: str, name: str) -> Callable[[ConcolicStr, object], object]:
    """str's own answer to one compare, followed while the solver reads the other side.

    A literal holding a character past the last one cvc5 holds is answered
    by str alone, and the downgrade names the compare's dunder. It is not
    NotImplemented: the literal's reflected compare would answer instead,
    and the line would never say the condition was lost.
    """
    followed = compare(op, getattr(str, name), _operand)
    downgrade = downgraded(str, name)

    def compute(self: ConcolicStr, other: object) -> object:
        return followed(self, other) if _within_cvc5(other) else downgrade(self, other)

    return compute


def _needle(args: tuple[object, ...]) -> Expression | None:
    """The symbolic form of what a taught search looks for, in the form pyct encodes.

    That form is one str argument the solver reads as it is. Any other call
    of the method is None.
    """
    if len(args) != 1 or not _within_cvc5(args[0]):
        return None
    return _operand(args[0])


def _search(
    name: str, answer: type[ConcolicBool] | type[ConcolicInt], *, raises: bool = False
) -> Callable[..., object]:
    """str's own answer to one search, carrying `[name, s, sub]`, as a tracked bool or int.

    A search that ``raises`` on a missing substring records whether sub is
    in s first (see `_found`). A call in a form pyct does not encode, a
    keyword included, goes to str's own method as written: its answer and a
    downgrade named by the method (``README.md › Rules › downgrades``), or
    the raise str makes of it.
    """
    operation = getattr(str, name)
    downgrade = downgraded(str, name)

    def compute(self: ConcolicStr, /, *args: object, **kwargs: object) -> object:
        form = None if kwargs else _needle(args)
        if form is None:
            return downgrade(self, *args, **kwargs)
        if raises:
            _found(self, form, args[0])
        expression = [name, self.expression, form]
        return answer(own(operation, self, *args), expression=expression, sink=self.sink)

    return compute


def _found(self: ConcolicStr, form: Expression, sub: object) -> None:
    """The fork a search takes on its way to a raise: `["in", sub, s]`, taken when sub is there.

    It goes in before str's own call, the way a division records its zero
    fork (``README.md › Rules › forks``): a missing sub raises ValueError out
    of that call, and the raising input's line already lists the fork,
    taken false. On every path past it sub is in s.
    """
    forked(self.sink, ["in", form, self.expression], own(str.__contains__, self, sub))


_CONTAINS_DOWNGRADE = downgraded(str, "__contains__")


def _contains(self: ConcolicStr, sub: object) -> object:
    """str's own answer to `sub in s`, carrying `["in", sub, s]` in Python's operand order.

    CPython tests the answer for truth where the `in` runs, so that is where
    the fork is recorded, and `not in` records the same fork with its side
    reversed (``README.md › Rules › forks``). A call in a form pyct does not
    encode is str's own answer and a `__contains__` downgrade.
    """
    form = _needle((sub,))
    if form is None:
        return _CONTAINS_DOWNGRADE(self, sub)
    expression = ["in", form, self.expression]
    return ConcolicBool(own(str.__contains__, self, sub), expression=expression, sink=self.sink)


def _position(value: object) -> int | None:
    """A position pyct encodes, a plain int or a plain bool, as the int it indexes with.

    Any other value is None.
    """
    return int(value) if isinstance(value, int) and type(value) in (int, bool) else None


def _bounds(key: object) -> list[Expression] | None:
    """The start and the stop of a slice pyct encodes, a missing bound as None.

    That slice has no step, and each bound it has is a position pyct encodes.
    Any other key is None.
    """
    if not isinstance(key, slice) or key.step is not None:
        return None
    ends = (key.start, key.stop)
    if not all(end is None or _position(end) is not None for end in ends):
        return None
    return [None if end is None else _position(end) for end in ends]


def _long_enough(self: ConcolicStr, index: int) -> None:
    """The fork an index takes on its way to a raise: whether s is long enough for it.

    `[">", ["len", s], i]` for an index of zero or more, and
    `[">=", ["len", s], -i]` for a negative one, which counts back from the
    end. It goes in before str's own index may raise IndexError, as `_found`
    does for ValueError. str's own length, not `len(s)`, which would record
    `__len__`.
    """
    length = own(str.__len__, self)
    measured: Expression = ["len", self.expression]
    if index >= 0:
        forked(self.sink, [">", measured, index], length > index)
    else:
        forked(self.sink, [">=", measured, -index], length >= -index)


_GETITEM_DOWNGRADE = downgraded(str, "__getitem__")


def _item(self: ConcolicStr, key: object) -> object:
    """str's own `s[i]` or `s[i:j]`, a tracked str carrying `["[]", s, i]` or `["[:]", s, i, j]`.

    An index records whether s is long enough first (see `_long_enough`). A
    slice clamps to the string, so it records no fork. A key in a form pyct
    does not encode is str's own answer and a `__getitem__` downgrade.
    """
    index = _position(key)
    if index is not None:
        _long_enough(self, index)
        expression = ["[]", self.expression, index]
        return ConcolicStr(own(str.__getitem__, self, key), expression=expression, sink=self.sink)
    bounds = _bounds(key)
    if bounds is None:
        return _GETITEM_DOWNGRADE(self, key)
    expression = ["[:]", self.expression, *bounds]
    return ConcolicStr(own(str.__getitem__, self, key), expression=expression, sink=self.sink)


def _one_str(args: tuple[object, ...]) -> list[Expression] | None:
    """The operand of a piece that takes one str, in the form pyct encodes, or None."""
    form = _needle(args)
    return None if form is None else [form]


def _replaced_exactly(old: object) -> bool:
    """Whether cvc5's replace_all is Python's replace for this old string.

    It is for a plain str with at least one character. For an empty one,
    cvc5 leaves the string as it is where Python puts the new string between
    every character, and a tracked old string may be empty.
    """
    return isinstance(old, str) and not isinstance(old, ConcolicStr) and str.__len__(old) > 0


def _replacement(args: tuple[object, ...]) -> list[Expression] | None:
    """The old and the new string of a replace pyct encodes, or None.

    That replace takes two str arguments the solver reads as they are, and
    no count, and cvc5 replaces its old string as Python does.
    """
    if len(args) != 2 or not all(_within_cvc5(arg) for arg in args):
        return None
    old, new = args
    if not _replaced_exactly(old) or not isinstance(new, str):
        return None
    return [_operand(old), _operand(new)]


def _piece(
    name: str, operands: Callable[[tuple[object, ...]], list[Expression] | None]
) -> Callable[..., object]:
    """str's own answer to one method that builds a str, as a tracked str carrying
    `[name, s, *operands]`.

    A call in a form pyct does not encode, a keyword included, is str's own
    answer and a downgrade named by the method (``README.md › Rules ›
    downgrades``).
    """
    operation = getattr(str, name)
    downgrade = downgraded(str, name)

    def compute(self: ConcolicStr, /, *args: object, **kwargs: object) -> object:
        forms = None if kwargs else operands(args)
        if forms is None:
            return downgrade(self, *args, **kwargs)
        expression = [name, self.expression, *forms]
        return ConcolicStr(own(operation, self, *args), expression=expression, sink=self.sink)

    return compute


def _reflected(self: ConcolicStr, other: object) -> object:
    """What the right side's own `__radd__` answers to `s + other`, or NotImplemented.

    With a plain str on the left, Python asks the right side's `__radd__`
    before str joins the two, and str has none of its own, so any type that
    has one is the target's or a library's: markupsafe's Markup answers, and
    numpy.str_ and int decline. A tracked str on the right joins as a str.
    """
    radd = None if isinstance(other, ConcolicStr) else getattr(type(other), "__radd__", None)
    return NotImplemented if radd is None else own(radd, other, self)


_ADD_DOWNGRADE = downgraded(str, "__add__")


def _appended(self: ConcolicStr, other: object) -> object:
    """str's own `s + other`, a tracked str carrying `["+", s, other]`.

    The right side's own `__radd__` answers first, as it does with a plain
    str on the left (see `_reflected`). Past one that declines, an other in
    a form pyct does not encode is str's own answer and an `__add__`
    downgrade, or str's own TypeError for a non-str.
    """
    if (answer := _reflected(self, other)) is not NotImplemented:
        return answer
    form = _needle((other,))
    if form is None:
        return _ADD_DOWNGRADE(self, other)
    expression = ["+", self.expression, form]
    return ConcolicStr(own(str.__add__, self, other), expression=expression, sink=self.sink)


def _joined_after(self: ConcolicStr, other: str) -> str:
    """str's own `other + s`: its concatenation with the operands the other way round."""
    return str.__add__(other, self)


# str has no `__radd__` of its own, so the downgrade is handed the concatenation it stands for
_RADD_DOWNGRADE = downgraded(str, "__radd__", calling=_joined_after)


def _prepended(self: ConcolicStr, other: object) -> object:
    """`other + s` with a str on the left that is not tracked, carrying `["+", other, s]`.

    Python asks a str subclass on the right before str's own concatenation,
    so `"x" + s` comes here. A non-str gets NotImplemented, and Python raises
    its own TypeError. A literal the solver cannot hold is str's own answer
    and a `__radd__` downgrade.
    """
    if not isinstance(other, str):
        return NotImplemented
    if not _within_cvc5(other):
        return _RADD_DOWNGRADE(self, other)
    expression = ["+", _operand(other), self.expression]
    return ConcolicStr(own(_joined_after, self, other), expression=expression, sink=self.sink)


class ConcolicStr(str):
    """A real str with a name and a sink.

    The operations taught below stay symbolic. Any other instance method str defines,
    except those left to it in `_KEPT`, is str's own and returns a plain value, with a
    downgrade in the sink naming what was lost: a method by its name, an operator by its
    dunder (``README.md › Rules › downgrades``). A taught search or piece called in a form
    pyct does not encode is str's own and a downgrade the same way.
    """

    expression: Expression
    sink: BranchSink

    # Python swaps the operands of a reflected compare itself, so `"b" < s` runs
    # `s.__gt__("b")` and prints [">", "s", "'b'"]; nothing here has to reflect anything.
    # str promises a bool from each, and a ConcolicBool is an int that is not a bool,
    # because bool cannot be subclassed; the override breaks that promise on purpose.
    __lt__ = _compare("<", "__lt__")  # pyrefly: ignore[bad-override]
    __le__ = _compare("<=", "__le__")  # pyrefly: ignore[bad-override]
    __gt__ = _compare(">", "__gt__")  # pyrefly: ignore[bad-override]
    __ge__ = _compare(">=", "__ge__")  # pyrefly: ignore[bad-override]
    __eq__ = _compare("==", "__eq__")  # pyrefly: ignore[bad-override]
    __ne__ = _compare("!=", "__ne__")  # pyrefly: ignore[bad-override]
    # a class body that defines __eq__ gets __hash__ = None unless it says otherwise
    __hash__ = str.__hash__
    __copy__ = copy_as_itself
    __deepcopy__ = copy_as_itself
    # a pickle holds the plain value and loads as a str, and writing it is a downgrade
    __reduce_ex__ = pickled(str, "__reduce_ex__")
    __reduce__ = pickled(str, "__reduce__")

    # a position or a count is a tracked int, so `s.find("x") < n` is one fork on s and n, and
    # `in`, `startswith` and `endswith` answer with a tracked bool for the reason the compares
    # do. index and rindex record their `in` fork before they may raise. A search takes any
    # arguments and hands a form it does not encode to str, so its signature is not str's;
    # the override breaks str's on purpose
    __contains__ = _contains  # pyrefly: ignore[bad-override]
    startswith = _search("startswith", ConcolicBool)  # pyrefly: ignore[bad-override]
    endswith = _search("endswith", ConcolicBool)  # pyrefly: ignore[bad-override]
    find = _search("find", ConcolicInt)  # pyrefly: ignore[bad-override]
    rfind = _search("rfind", ConcolicInt)  # pyrefly: ignore[bad-override]
    count = _search("count", ConcolicInt)  # pyrefly: ignore[bad-override]
    index = _search("index", ConcolicInt, raises=True)  # pyrefly: ignore[bad-override]
    rindex = _search("rindex", ConcolicInt, raises=True)  # pyrefly: ignore[bad-override]

    # a piece of a tracked str is a tracked str, so a compare or a search on it is a fork on s.
    # An index records whether s is long enough before it may raise. A piece hands a form it
    # does not encode to str, so its signature is not str's; the override breaks str's on purpose
    __getitem__ = _item  # pyrefly: ignore[bad-override]
    __add__ = _appended  # pyrefly: ignore[bad-override]
    __radd__ = _prepended
    replace = _piece("replace", _replacement)  # pyrefly: ignore[bad-override]
    removeprefix = _piece("removeprefix", _one_str)  # pyrefly: ignore[bad-override]
    removesuffix = _piece("removesuffix", _one_str)  # pyrefly: ignore[bad-override]

    def __new__(cls, value: str, *, expression: Expression, sink: BranchSink) -> ConcolicStr:
        self = super().__new__(cls, value)
        self.expression = expression
        self.sink = sink
        return self

    def __bool__(self) -> bool:
        # str has no __bool__ and Python falls to __len__; this one comes first. The empty
        # string is the one value that takes the other side, written as repr writes it
        return forked(self.sink, ["!=", self.expression, "''"], own(str.__len__, self) > 0)


# the class body above is everything ConcolicStr teaches. The rest of str differs only in the
# name it calls and records, so the derivation writes it
downgrade_the_rest(ConcolicStr, str, kept=_KEPT, inherited=())
