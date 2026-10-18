"""`%` formatting with a plain str format and a tracked operand: `"<b>%s</b>" % (s,)`.

Python copies each operand's text into a new plain str, so the condition
is lost there. `pyct.intercept` hands ``<str literal> % <operand>`` to
`mod`, or to `fstring_mod` where CPython compiles it as an f-string, and
``<format> % (<tuple display>)`` and ``<name> %= (<tuple display>)`` to
the call `formatter` or `in_place_formatter` hands back for the left side;
a tracked str on the right of a plain format reaches `formatted` through
its own `__rmod__`, which Python asks first.

A format that is exactly a str, given a tracked value, is formatted piece
by piece by Python's own `%`, one conversion at a time, each on the plain
value of a tracked operand, so the text and any error are Python's. The
answer is a tracked str, ``["%", fmt, operand]``, with the operand a tuple
``["()", ...]`` when the target wrote one, where each tracked operand has
the conversion `%s` on a str, int or bool, or `%d` or `%i` on an int or
bool, with no flag, width, precision or length (`FOLLOWED`). A format that
is `%s` alone answers with the operand's own text, as Python's own `%`
does. A plain int, bool or str operand is a literal in the expression, and
any other plain operand is written into the format as the text it gave.
Any other conversion of a tracked operand, a format read through a key or
a ``*``, or a text the solver cannot hold, gives Python's text, plain, and
a downgrade named `__mod__`.
"""

from __future__ import annotations

import ast
import functools
import operator
import re
from collections.abc import Callable, Iterable
from typing import Any, NamedTuple, cast

from pyct.core import numbers
from pyct.core.branch import BranchSink, Downgrade, Expression, caller_site
from pyct.core.escapes import lost
from pyct.core.str_operands import within_cvc5
from pyct.core.values import BASES, downgraded, own, plain

# a conversion Python reads with one operand and no key or `*`, as its flags, width, precision
# and length, then its letter; or `%%`, a percent sign
_CONVERSION = re.compile(r"%%|%([-+ #0]*\d*(?:\.\d*)?[hlL]?)([diouxXeEfFgGcrsa])")

# the letters pyct follows on a tracked operand with nothing between `%` and the letter, by the
# base type of the operand
FOLLOWED: dict[str, frozenset[type]] = {
    "s": frozenset({str, int, bool}),
    "d": frozenset({int, bool}),
    "i": frozenset({int, bool}),
}

# the base types whose tracked value Python formats as its plain value
_SCALARS = frozenset({str, int, bool, float})


class Spec(NamedTuple):
    """One conversion as the format writes it, ``%5.2f`` say, with its letter and whether
    nothing stands between `%` and the letter."""

    text: str
    letter: str
    bare: bool


type Token = str | Spec


@functools.lru_cache(maxsize=512)
def tokens(fmt: str) -> tuple[Token, ...] | None:
    """The format as its literal text and its conversions, in order, or None for a format that
    reads its operands through a key or a ``*``, or that Python refuses.

    A percent sign `%%` is the text ``%``. Each conversion reads one operand.
    """
    found: list[Token] = []
    at = 0
    for match in _CONVERSION.finditer(fmt):
        if "%" in fmt[at : match.start()]:
            return None
        found.append(fmt[at : match.start()])
        at = match.end()
        letter = match.group(2)
        found.append("%" if letter is None else Spec(match.group(0), letter, not match.group(1)))
    if "%" in fmt[at:]:
        return None
    found.append(fmt[at:])
    return tuple(token for token in found if token)


def _base(value: object) -> type | None:
    return BASES.get(type(value))


def _plain(value: object) -> object:
    """A tracked str, int, bool or float as Python's own value, and any other value as itself."""
    base = _base(value)
    return plain(value, base) if base is not None and base in _SCALARS else value


def holds_tracked(right: object) -> bool:
    """Whether the right side of a `%` is a tracked value or holds one as an item of a tuple or
    a value of a dict. Only types are read.

    A plain `%` at a substituted spot runs it every time, so it calls
    nothing it can do itself.
    """
    kind = type(right)
    if kind is tuple or (kind not in BASES and isinstance(right, tuple)):
        items: Iterable[object] = right  # pyrefly: ignore[bad-assignment]
    elif kind is dict:
        items = right.values()  # pyrefly: ignore[missing-attribute]
    else:
        return kind in BASES
    # a loop, not `any`: on two items it runs in about 47 ns against 114 ns
    for item in items:  # noqa: SIM110
        if type(item) in BASES:
            return True
    return False


def formatted(fmt: str, right: object) -> object:
    """``fmt % right`` for a plain str format whose right side holds a tracked value."""
    read = tokens(fmt)
    items = tuple(cast(tuple[object, ...], right)) if isinstance(right, tuple) else (right,)
    specs = [token for token in read or () if isinstance(token, Spec)]
    if read is None or len(specs) != len(items):
        return _as_python(fmt, right, keyed=read is None)
    if len(read) == 1 and specs[0].text == "%s" and _followed(specs[0], items[0]):
        # `%s` alone: Python's own `%` answers with the text `str` gives the operand
        return own(str, items[0])
    return _Pieces(read, items).answer(isinstance(right, tuple))


def _as_python(fmt: str, right: object, *, keyed: bool) -> object:
    """Python's own answer, on the plain values of tracked operands, or its raise.

    A format read through a key or a ``*`` may read any tracked value, so it
    is a downgrade. Any other format whose conversions do not match the
    operands one to one either raises or, with a mapping on the right and no
    conversion, reads nothing.
    """
    plain_right: object = _plain(right)
    if isinstance(right, tuple):
        plain_right = tuple(map(_plain, cast(tuple[object, ...], right)))
    elif type(right) is dict:
        mapping = cast(dict[object, object], right)
        plain_right = {key: _plain(value) for key, value in mapping.items()}
    answer = own(operator.mod, fmt, plain_right)
    if keyed:
        _downgrade(_sink_of(right))
    return answer


def _sink_of(right: object) -> BranchSink:
    """The sink of the first tracked value the right side is or holds."""
    if _base(right) is not None:
        return cast(Any, right).sink
    held = cast(dict[object, object], right).values() if type(right) is dict else right
    return next(cast(Any, item).sink for item in cast(Any, held) if _base(item) is not None)


def _followed(spec: Spec, item: object) -> bool:
    """Whether pyct follows this conversion of a tracked operand."""
    return spec.bare and _base(item) in FOLLOWED.get(spec.letter, ())


def _downgrade(sink: BranchSink) -> None:
    lost(sink, Downgrade(name="__mod__", site=caller_site()))


class _Pieces:
    """A format's text and its expression, built one conversion at a time."""

    def __init__(self, read: tuple[Token, ...], items: tuple[object, ...]) -> None:
        self.texts: list[str] = []
        # the format as the expression writes it, and each operand that stays an operand
        self.written: list[str] = []
        self.forms: list[Expression] = []
        self.sink: BranchSink | None = None
        self.lost = False
        operands = iter(items)
        for token in read:
            if isinstance(token, Spec):
                self._convert(token, next(operands))
            else:
                self.texts.append(token)
                self.written.append(token.replace("%", "%%"))

    def _convert(self, spec: Spec, item: object) -> None:
        """One conversion: its text, and the operand's form or the text written into the
        format in its place."""
        # an object of the target's own may hand back a tracked str from `__str__`: its text
        text = str.__str__(own(operator.mod, spec.text, (_plain(item),)))
        self.texts.append(text)
        if _base(item) is not None:
            if self.sink is None:
                self.sink = cast(Any, item).sink
            self.lost = self.lost or not _followed(spec, item)
            self.written.append(spec.text)
            self.forms.append(cast(Any, item).expression)
            return
        form = _literal(item)
        if form is None:
            self.lost = self.lost or not within_cvc5(text)
            self.written.append(text.replace("%", "%%"))
            return
        self.written.append(spec.text)
        self.forms.append(form)

    def answer(self, tupled: bool) -> object:
        """The text, tracked where it follows a tracked operand, plain where none is."""
        text = "".join(self.texts)
        if self.sink is None:
            return text
        fmt = _text_literal("".join(self.written))
        if self.lost or fmt is None:
            _downgrade(self.sink)
            return text
        operand = ["()", *self.forms] if tupled else self.forms[0]
        return numbers.tracked(text, ["%", fmt, operand], self.sink)


def _literal(item: object) -> Expression | None:
    """A plain operand as the expression writes it: an int or a bool as itself, a str as repr
    writes it, or None for any other value."""
    if type(item) is int or type(item) is bool:
        return cast(int, item)
    return _text_literal(cast(str, item)) if type(item) is str else None


def _text_literal(text: str) -> str | None:
    """A plain str as repr writes it, or None for one holding a character the solver cannot."""
    return str.__repr__(text) if within_cvc5(text) else None


def mod(fmt: str, right: object, /) -> object:
    """``fmt % right`` where the target writes a str literal's `%`, or one a `formatter` hands
    back runs.

    A right side holding a tracked value is formatted here; any other is
    Python's own `%`, with its errors.
    """
    if holds_tracked(right):
        return formatted(fmt, right)
    return fmt % right


def fstring_mod(fmt: str, right: tuple[object, ...], /) -> object:
    """``fmt % (<tuple display>)`` where the target writes a str literal's `%` that CPython
    compiles as the f-string it means, as `pyct.intercept.percents` checks in the compiled code.

    A right side holding a tracked value is formatted as `mod` formats it;
    any other runs that f-string, compiled from the same shape, so its text,
    its type and the `__format__` spec it hands each operand are CPython's.
    """
    if holds_tracked(right):
        return formatted(fmt, right)
    return _as_compiled(fmt, len(right))(*right)


@functools.lru_cache(maxsize=256)
def _as_compiled(fmt: str, count: int) -> Callable[..., object]:
    """``lambda _0, ..., _n: fmt % (_0, ..., _n)``, which CPython compiles as the target's own
    `%` of that format and a tuple display of as many operands."""
    names = [f"_{at}" for at in range(count)]
    held = ast.Tuple(elts=[ast.Name(id=name, ctx=ast.Load()) for name in names], ctx=ast.Load())
    body = ast.BinOp(left=ast.Constant(value=fmt), op=ast.Mod(), right=held)
    arguments = ast.arguments(
        posonlyargs=[ast.arg(arg=name) for name in names],
        args=[],
        kwonlyargs=[],
        kw_defaults=[],
        defaults=[],
    )
    tree = ast.fix_missing_locations(ast.Expression(body=ast.Lambda(args=arguments, body=body)))
    return eval(compile(tree, "<pyct format>", "eval"))  # noqa: S307 - a tree built here


def formatter(left: object, /) -> Callable[[object], object]:
    """What ``left % (<tuple display>)`` calls with its right side, ``left`` not a literal.

    A format that is exactly a str gets `mod`. Any other left side gets
    Python's own `%` bound to it, which runs in C: the target's own
    `__mod__` runs with no frame of pyct's above it.
    """
    return functools.partial(mod if type(left) is str else operator.mod, left)


def in_place_formatter(left: object, /) -> Callable[[object], object]:
    """What ``<name> %= (<tuple display>)`` calls with its right side, as `formatter` answers,
    but Python's own `%=` for any left side but a str, which has no `__imod__` of its own."""
    return functools.partial(mod if type(left) is str else operator.imod, left)


# str's own reflected `%`, which answers NotImplemented to anything but a str
_RMOD_DOWNGRADE = downgraded(str, "__rmod__")


def reflected(self: str, other: object) -> object:
    """A tracked str's `__rmod__`: ``other % self``, which Python asks first for a str on the
    left. A format that is exactly a str is formatted as `formatted` formats it."""
    if type(other) is str:
        return formatted(other, self)
    return _RMOD_DOWNGRADE(self, other)


# the router blame reads through: a raise under it is Python's own `%` or the target's
PASSING = frozenset({mod.__code__, fstring_mod.__code__})
