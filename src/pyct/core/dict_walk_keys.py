"""The key a dict's own walk hands out: one the solver may choose at its pass in a small dict
(let-the-solver-choose-a-small-dict-s-walk-key).

The target's own `for`, a statement or a comprehension, over a dict, its keys, its values or its
items, hands out at each pass a tracked str or int written `["key", A, i]`: the key a walk of
the argument A reads at pass i, `list(A)[i]`. It equals the key Python read, and answers every
operation as that key does, so a compare on it is a fork, as on any tracked str or int. It does
so only where the dict has a form, nothing changed it since the input, its keys are all plain
strs or all plain ints, and its values all ints or strs, whatever its size: an answer that grows
the dict walks it as the path did. The solver chooses keys only in a dict of the input of at
most ``MOST_KEYS`` keys (``solver.walk_keys``). Every other walk hands out keys as
``dict_handouts`` says: a changed or marked dict, `list(d)`, `sorted(d)`, `reversed(d)`,
`next(iter(d))`, `dict(d)`, unpacking, and a walk in code outside the target's package.

A lookup of a walk key in an unchanged dict made from the same argument is a fact: the walk
read that key, so the dict holds it. A change under one keeps that walk's key where the input
had it, a fact that it equals the plain key there, and is made under the plain key.
"""

from __future__ import annotations

import dis
import sys
import types

from pyct.core.branch import PYCT_DIR, Expression, Fact, caller_site
from pyct.core.dict_compares import written_key
from pyct.core.dict_state import DictState
from pyct.core.ints import ConcolicInt
from pyct.core.list_state import plain
from pyct.core.strs import ConcolicStr
from pyct.core.walk_key_escapes import WALK_KEY

# the most keys a dict of the input holds for the solver to choose its walk's keys: each key it
# chooses is looked up in every key the dict holds, and in 200 int keys one ask with 3 chosen
# keys took 0.24 s and one with 10 1.5 s (cvc5 1.3.4, macOS arm64, load 4 to 8)
MOST_KEYS = 200

# the instruction a `for` statement and a comprehension run to start a walk; a call that walks,
# `list(d)` or `sorted(d)`, runs a call instead
_GET_ITER = dis.opmap["GET_ITER"]

# the module whose `len` pyct binds in the builtins of each module of the target's package
_BOUND = "pyct.core.bound"


def walk_keyed(self: DictState) -> bool:
    """Whether the walk starting now hands out walk keys: an unchanged dict of plain str or int
    keys and int or str values, walked by the target's own `for`."""
    if self.expression is None or self.log or self.unforked or self.popped or self.reordered:
        return False
    if not _typed_alike(self):
        return False
    return _own_for(sys._getframe(1))


def _typed_alike(self: DictState) -> bool:
    """Whether the dict's keys are all plain strs or all plain ints, and its values ints or
    strs, so the solver reads every key a chosen one may equal and the value under it."""
    kinds = {type(key) for key in dict.keys(self)}
    if len(kinds) > 1 or not kinds <= {str, int}:
        return False
    return all(type(plain(held)) in (str, int) for held in dict.values(self))


def _own_for(frame: types.FrameType | None) -> bool:
    """Whether the innermost frame outside pyct starts a walk with a `for` of its own, in a
    module of the target's package, whose builtins pyct binds."""
    while frame is not None and frame.f_code.co_filename.startswith(PYCT_DIR):
        frame = frame.f_back
    if frame is None or frame.f_code.co_code[frame.f_lasti] != _GET_ITER:
        return False
    return getattr(frame.f_builtins.get("len"), "__module__", None) == _BOUND


def handed(self: DictState, key: object, at: int) -> object:
    """The walk key for ``key`` at pass ``at``: a tracked copy of it that names the pass."""
    expression: Expression = [WALK_KEY, self.expression, at]
    if type(key) is str:
        return ConcolicStr.made(key, expression, self.sink)
    assert type(key) is int
    return ConcolicInt.made(key, expression, self.sink)


def place(self: DictState, key: object) -> Expression:
    """Where a walk read a walk key: at its pass, whichever key the solver chooses there."""
    assert isinstance(key, ConcolicStr | ConcolicInt)
    return ["walked", self.expression, key.expression]


def of_the_argument(self: DictState, key: object) -> bool:
    """Whether ``key`` is a walk key of the argument this dict came from."""
    if type(key) is not ConcolicStr and type(key) is not ConcolicInt:
        return False
    expression = key.expression
    return (
        isinstance(expression, list)
        and len(expression) == 3
        and expression[0] == WALK_KEY
        and self.expression is not None
        and expression[1] == self.expression
    )


def held(self: DictState, key: object, name: str, raising: bool) -> bool:
    """Whether a lookup of a walk key is the fact that the dict holds it: the dict is unchanged
    since the input, so it holds the key its walk read. Recorded where it is, and True."""
    if self.log or self.unforked or self.reordered or not of_the_argument(self, key):
        return False
    if not dict.__contains__(self, plain(key)):
        return False
    assert isinstance(key, ConcolicStr | ConcolicInt)
    test: Expression = ["in", key.expression, self.expression]
    self.sink.append(Fact(test, True, caller_site(), raising, lost_as=name))
    return True


def pinned(self: DictState, key: object) -> object:
    """A key a change is made under: a walk key of the argument as its plain key, after the fact
    that it is that key, so the change is the same on every input that takes the path; any other
    key as it is."""
    if not of_the_argument(self, key):
        return key
    assert isinstance(key, ConcolicStr | ConcolicInt)
    bare = plain(key)
    self.sink.append(Fact(["==", key.expression, written_key(bare)], True, caller_site()))
    return bare
