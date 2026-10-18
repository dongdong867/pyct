"""The assignments pyct substitutes where the target writes them: an unpack into a fixed count.

Python's own unpack reads how many items a value holds without asking the
value, so a split's list cannot fork on its count there. An assignment
whose one target is a tuple or a list, with no star or one star, hands its
value to pyct first, with the number of places the target has:
``a, b = s.split(",")`` becomes ``a, b = __pyct_unpack__(s.split(","), 2)``,
and ``first, *rest = parts`` becomes
``first, *rest = __pyct_unpack_starred__(parts, 1)``, the count there being
the places other than the star (`pyct.core.substitutes.unpack`). A nested
tuple in the target is one place. pyct hands back the same items, so
Python unpacks them, and raises its own error, as written.

A value written as a tuple or list display, as ``a, b = b, a``, stays as
written: CPython builds and unpacks it with no value pyct could follow. A
chained assignment stays as written too.

The value is the statement's own node, moved into the call, which takes the
value's position, or the attribute's name where the value's last
instruction is there (`positions.after_the_value`), and so does the count.
The name sits where the value's first instruction does
(`positions.Parts.named`). So the call adds no line.
"""

from __future__ import annotations

import ast

from pyct.intercept.positions import Parts, after_the_value

_COUNTED = "__pyct_unpack__"
_STARRED = "__pyct_unpack_starred__"
BOUND: dict[str, str] = {_COUNTED: "unpack", _STARRED: "unpack_starred"}

# a value CPython builds in place for the unpack, which pyct leaves as written
_DISPLAYS = (ast.Tuple, ast.List)


def hand_over(assignment: ast.Assign, parts: Parts) -> None:
    """Hand the value of an unpack into a fixed count to pyct, in place; any other assignment
    stays as written."""
    if len(assignment.targets) != 1 or isinstance(assignment.value, _DISPLAYS):
        return
    target = assignment.targets[0]
    if not isinstance(target, _DISPLAYS):
        return
    stars = sum(isinstance(place, ast.Starred) for place in target.elts)
    if stars > 1:
        return
    value = assignment.value
    name = _STARRED if stars else _COUNTED
    counted = ast.Constant(value=len(target.elts) - stars)
    call = ast.Call(func=parts.named(name, value), args=[value, counted], keywords=[])
    assignment.value = after_the_value(call, value)
    ast.copy_location(counted, call)
