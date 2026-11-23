"""What a loss site's code says, read from its file without running it: the site's code as written,
its lines, and the name of each value going in (`pyct.core.entry.losses`).

The site's node is the part of the code that starts at its line and column, as a no-fork
condition's lost source finds it (`pyct.results.sources`), whose kind fits the downgrade: a
call written as the downgrade names it, or an operator, a compare, a subscript or an augmented
assignment whose dunder it is. The values going in are the node's parts in the order a
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
from pyct.results.sources import written_name

# the parts a loss site's node can be
_NODES = (ast.BinOp, ast.UnaryOp, ast.Compare, ast.Call, ast.Subscript, ast.AugAssign)
# each binary operator's word, as its dunders are written
_OPERATORS: dict[type[ast.operator], str] = {
    ast.Add: "add",
    ast.Sub: "sub",
    ast.Mult: "mul",
    ast.MatMult: "matmul",
    ast.Div: "truediv",
    ast.FloorDiv: "floordiv",
    ast.Mod: "mod",
    ast.Pow: "pow",
    ast.LShift: "lshift",
    ast.RShift: "rshift",
    ast.BitOr: "or",
    ast.BitXor: "xor",
    ast.BitAnd: "and",
}
# each unary operator's dunder
_UNARY: dict[type[ast.unaryop], str] = {
    ast.USub: "__neg__",
    ast.UAdd: "__pos__",
    ast.Invert: "__invert__",
    ast.Not: "__bool__",
}
# the dunders a compare calls
_COMPARES = frozenset(("__lt__", "__le__", "__gt__", "__ge__", "__eq__", "__ne__", "__contains__"))
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
    """The node that starts at the site and whose kind fits the downgrade's name (`_fit`): a call
    named as the downgrade names it before an operator, and the innermost of two that fit
    alike. None when no node fits."""
    fits = [
        (fit, node)
        for node in ast.walk(tree)
        if isinstance(node, _NODES) and (node.lineno, node.col_offset) == (site.line, site.col)
        for fit in [_fit(node, name)]
        if fit is not None
    ]
    best = min((fit for fit, _ in fits), default=None)
    return next((node for fit, node in reversed(fits) if fit == best), None)


def _fit(node: ast.expr | ast.stmt, name: str) -> int | None:
    """How well the node fits a downgrade of ``name``: 0 for a call whose callee is written as
    the name, or ends in it, or in its operator's word, such as ``pow`` for ``__pow__``; 1 for
    an operator, a compare or a subscript whose dunder is the name; None for no fit."""
    if isinstance(node, ast.Call):
        callee = written_name(node.func)
        words = {name, _bare(name)}
        return 0 if callee in words or callee.rsplit(".", 1)[-1] in words else None
    if isinstance(node, (ast.BinOp, ast.AugAssign)):
        word = _OPERATORS.get(type(node.op))
        forms = {f"__{word}__", f"__r{word}__", f"__i{word}__"}
        return 1 if name in forms else None
    if isinstance(node, ast.UnaryOp):
        return 1 if name == _UNARY.get(type(node.op)) else None
    if isinstance(node, ast.Compare):
        return 1 if name in _COMPARES else None
    return 1 if isinstance(node, ast.Subscript) and name == "__getitem__" else None


def _bare(name: str) -> str:
    """A dunder's word, a reflected one's without its ``r``: ``pow`` for ``__rpow__``."""
    if not (name.startswith("__") and name.endswith("__")):
        return name
    return name[3:-2] if name in _REFLECTED else name[2:-2]


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
