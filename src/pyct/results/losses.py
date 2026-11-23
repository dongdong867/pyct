"""What a loss site's code says, read from its file without running it: the site's code as written,
its lines, and the name of each value going in (`pyct.core.entry.losses`).

The site's node is the part of the code that starts at its line and column, as a no-fork
condition's lost source finds it (`pyct.results.sources`): an operator, a call, a compare, a
subscript or an augmented assignment. The values going in are the node's parts in the order a
loss run records them: an operation's receiver, the left operand or, for a reflected
operation, the right one, then its other operands and arguments; a `math` call's arguments, by
position then by keyword; and a watched call's arguments that are no constant, since the watch
is given no constant. Each is named as the code writes it when that is a name, and ``arg1``,
``arg2`` and so on by its position otherwise, as is a second value with a name already taken.
An operation's or a `math` call's constant operand is left out, since it is the same in every
run. When no node fits, each value is named by its position.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from pyct.core.foundation.branch import LossKind, Site

# the parts a loss site's node can be
_NODES = (ast.BinOp, ast.UnaryOp, ast.Compare, ast.Call, ast.Subscript, ast.AugAssign)
# the reflected operations, whose receiver is the right operand
_REFLECTED = frozenset(
    f"__r{name}__"
    for name in (
        "add",
        "sub",
        "mul",
        "matmul",
        "truediv",
        "floordiv",
        "mod",
        "divmod",
        "pow",
        "lshift",
        "rshift",
        "and",
        "xor",
        "or",
    )
)


@dataclass(frozen=True)
class LossCode:
    """A loss site's code: as written, its first and last line, and the parameter each value going
    in is named, None for a constant left out."""

    written: str
    lines: tuple[int, int]
    names: tuple[str | None, ...]


def loss_code(site: Site, name: str, kind: LossKind, count: int) -> LossCode:
    """The code of the loss site at ``site``, whose downgrade is ``name`` of ``kind`` and whose
    runs hold ``count`` values going in."""
    read = _read(site.file)
    node = None if read is None else _node(read[1], site, name)
    parts = None if node is None else _parts(node, name, kind)
    if read is None or node is None or parts is None or len(parts) != count:
        return LossCode(name, (site.line, site.line), _named([None] * count, kind))
    written = ast.get_source_segment(read[0], node) or ast.unparse(node)
    return LossCode(written, (node.lineno, node.end_lineno or node.lineno), _named(parts, kind))


def _read(file: str) -> tuple[str, ast.Module] | None:
    """The file's source and its tree, or None when it does not read or parse."""
    try:
        with open(file, encoding="utf-8") as opened:
            source = opened.read()
        return source, ast.parse(source, filename=file)
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def _node(tree: ast.Module, site: Site, name: str) -> ast.expr | ast.stmt | None:
    """The innermost node that starts at the site and can be its loss: a call by its method's
    name when it calls one by that name."""
    found: list[ast.expr | ast.stmt] = [
        node
        for node in ast.walk(tree)
        if isinstance(node, _NODES) and (node.lineno, node.col_offset) == (site.line, site.col)
    ]
    named = [
        node
        for node in found
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == name
    ]
    return (named or found or [None])[-1]


def _parts(node: ast.AST, name: str, kind: LossKind) -> list[ast.expr] | None:
    """The node's parts that give the values going in, in the order a loss run records them."""
    if isinstance(node, ast.Call):
        arguments = [*node.args, *(keyword.value for keyword in node.keywords)]
        if kind is LossKind.CALL:
            return [each for each in arguments if not isinstance(each, ast.Constant)]
        if kind is LossKind.OPERATION and isinstance(node.func, ast.Attribute):
            return [node.func.value, *arguments]
        return _receiver_first(arguments, name)
    if kind is not LossKind.OPERATION:
        return None
    return _operands(node, name)


def _operands(node: ast.AST, name: str) -> list[ast.expr] | None:
    """An operator's, a compare's, a subscript's or an augmented assignment's operands, the
    receiver first."""
    if isinstance(node, ast.BinOp):
        return _receiver_first([node.left, node.right], name)
    if isinstance(node, ast.AugAssign):
        return [node.target, node.value]
    if isinstance(node, ast.UnaryOp):
        return [node.operand]
    if isinstance(node, ast.Compare):
        return [node.left, *node.comparators]
    if isinstance(node, ast.Subscript):
        return [node.value, node.slice]
    return None


def _receiver_first(parts: list[ast.expr], name: str) -> list[ast.expr]:
    """The parts with a reflected operation's receiver, the second, first."""
    if name in _REFLECTED and len(parts) >= 2:
        return [parts[1], parts[0], *parts[2:]]
    return parts


def _named(parts: list[ast.expr] | list[None], kind: LossKind) -> tuple[str | None, ...]:
    """Each part's parameter name: its own name when it is one not taken yet, else its
    position's; None for a constant an operation or a `math` call leaves out."""
    names: list[str | None] = []
    for at, part in enumerate(parts, start=1):
        if isinstance(part, ast.Constant) and kind is not LossKind.CALL:
            names.append(None)
        elif isinstance(part, ast.Name) and part.id not in names:
            names.append(part.id)
        else:
            names.append(f"arg{at}")
    return tuple(names)
