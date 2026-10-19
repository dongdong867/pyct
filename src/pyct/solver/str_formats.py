"""A `%` format written as the concatenation it is.

Core writes ``fmt % operand`` on a plain format as ``["%", fmt, operand]``: ``fmt`` the format as
repr writes it, and ``operand`` the one operand or a tuple of them, ``["()", ...]``
(`pyct.core.str_formats`). Each conversion of a tracked operand is `%s`, whose text is the text
`str` writes, or `%d` or `%i`, whose text is the text `str` writes for the int; each plain
operand is an int, a bool or a str literal, whose text Python writes here, and the format's own
text stands between them. The condition means what it meant; only the way it is written
changes.
"""

import ast

from pyct.core.branch import Expression
from pyct.core.str_formats import Spec, tokens

# the head core writes for a format
FORMAT = "%"


def is_format(node: list[Expression]) -> bool:
    """Whether a part is a `%` on a format, whose left operand is a str literal, rather than an
    int's remainder."""
    return node[0] == FORMAT and isinstance(node[1], str) and node[1][:1] in ("'", '"')


def concatenated(fmt: Expression, operand: Expression) -> Expression:
    """``fmt % operand`` as its pieces joined, the empty string for none."""
    written = tokens(ast.literal_eval(str(fmt)))
    if written is None:
        raise ValueError(f"pyct cannot render the format {fmt}: it reads no operand one to one")
    tupled = isinstance(operand, list) and operand[0] == "()"
    items = iter(operand[1:] if isinstance(operand, list) and tupled else [operand])
    pieces: list[Expression] = []
    text = ""
    for token in written:
        piece = token if not isinstance(token, Spec) else _converted(token, next(items))
        if isinstance(piece, str):
            text += piece
            continue
        if text:
            pieces.append(str.__repr__(text))
            text = ""
        pieces.append(piece)
    if text or not pieces:
        pieces.append(str.__repr__(text))
    return pieces[0] if len(pieces) == 1 else ["+", *pieces]


def _converted(spec: Spec, item: Expression) -> str | list[Expression]:
    """One conversion: a plain operand's text, as Python writes it, or a tracked operand's
    text as a term, `str(x)` for `%s` and `str(int(x))` for `%d` and `%i`."""
    if _plain(item):
        return spec.text % (_value(item),)
    return ["str", item] if spec.letter == "s" else ["str", ["int", item]]


def _plain(item: Expression) -> bool:
    """Whether an operand is plain: an int, a bool, or a str literal, never a leaf's name."""
    if isinstance(item, str):
        return item[:1] in ("'", '"')
    return isinstance(item, int)


def _value(item: Expression) -> object:
    """A plain operand's value: an int or a bool as it is, a str literal as Python reads it."""
    return ast.literal_eval(item) if isinstance(item, str) else item
