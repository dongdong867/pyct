"""The concolic str: a real str that also carries its symbolic form."""

from __future__ import annotations

from collections.abc import Callable

from pyct.core.bools import ConcolicBool, compare
from pyct.core.branch import BranchSink, Expression
from pyct.core.ints import ConcolicInt
from pyct.core.values import copy_as_itself, downgrade_the_rest, downgraded, forked, own

# the `ConcolicStr` body below is the taught set: the compares, the truth test and the searches
# it writes stay symbolic, and a copy is the value itself. The tuple here names what is left to
# str on purpose, and the derivation at the bottom of the file downgrades every other method str
# defines, plain methods and operators alike. str defines `__str__` and `__format__` itself,
# so nothing inherited needs naming.

# not the target's path: `__hash__`, `__repr__`, the pickling hook and the rest of the object
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


def _search(name: str, answer: type[ConcolicBool] | type[ConcolicInt]) -> Callable[..., object]:
    """str's own answer to one search, carrying `[name, s, sub]`, as a tracked bool or int.

    A call in a form pyct does not encode is str's own answer and a
    downgrade named by the method (``README.md › Rules › downgrades``).
    """
    operation = getattr(str, name)
    downgrade = downgraded(str, name)

    def compute(self: ConcolicStr, *args: object) -> object:
        form = _needle(args)
        if form is None:
            return downgrade(self, *args)
        expression = [name, self.expression, form]
        return answer(own(operation, self, *args), expression=expression, sink=self.sink)

    return compute


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


class ConcolicStr(str):
    """A real str with a name and a sink.

    The operations taught below stay symbolic. Any other instance method str defines,
    except those left to it in `_KEPT`, is str's own and returns a plain value, with a
    downgrade in the sink naming what was lost: a method by its name, an operator by its
    dunder (``README.md › Rules › downgrades``). A taught search called in a form pyct
    does not encode is str's own and a downgrade the same way.
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

    # a position is a tracked int, so `s.find("x") < n` is one fork on s and n, and `in` is a
    # tracked bool for the reason the compares are. A search takes whatever arguments it is
    # given and hands a form it does not encode to str, so its signature is not str's; the
    # override breaks str's on purpose
    __contains__ = _contains  # pyrefly: ignore[bad-override]
    find = _search("find", ConcolicInt)  # pyrefly: ignore[bad-override]

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
