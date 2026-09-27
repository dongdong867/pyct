"""The fork line's parentheses: Python reads the line as the condition, and needs each pair."""

import ast
import json
import random

from pyct.core.branch import Branch, Expression, Site
from pyct.results.coverage import Coverage
from pyct.results.record import InputRecord
from pyct.results.trace import render_trace

COVERAGE = Coverage(covered={"m.py": frozenset({5})}, lines={"m.py": frozenset({5})})

# the operators core writes between two operands, and the one it writes before one
BINARY = ("<", "==", "in", "|", "^", "&", "<<", "+", "-", "*", "//", "%", "**")
LEAVES: tuple[Expression, ...] = ("x", "y", 0, 3, -2, True, "'a'")

# Python's own names for what it parsed, spelled as core writes the head
COMPARED: dict[type, str] = {ast.Lt: "<", ast.Eq: "==", ast.In: "in"}
COMBINED: dict[type, str] = {
    ast.BitOr: "|",
    ast.BitXor: "^",
    ast.BitAnd: "&",
    ast.LShift: "<<",
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.FloorDiv: "//",
    ast.Mod: "%",
    ast.Pow: "**",
}


def _tree(chance: random.Random, depth: int) -> Expression:
    """A condition core could write, of at most this depth."""
    pick = chance.random()
    if depth == 0 or pick < 0.2:
        return chance.choice(LEAVES)
    if pick < 0.35:
        return ["-", _tree(chance, depth - 1)]
    return [chance.choice(BINARY), _tree(chance, depth - 1), _tree(chance, depth - 1)]


def _read(node: ast.expr) -> object:
    """What Python parsed, as a nested list: a chain of compares reads as its own head."""
    if isinstance(node, ast.Compare):
        heads = [COMPARED[type(op)] for op in node.ops]
        return [" ".join(heads), _read(node.left), *(_read(part) for part in node.comparators)]
    if isinstance(node, ast.BinOp):
        return [COMBINED[type(node.op)], _read(node.left), _read(node.right)]
    if isinstance(node, ast.UnaryOp):
        return ["-", _read(node.operand)]
    if isinstance(node, ast.Name):
        return node.id
    assert isinstance(node, ast.Constant), ast.dump(node)
    return repr(node.value) if isinstance(node.value, str) else node.value


def _meant(expression: Expression) -> object:
    """The condition as Python parses its text: a negative number is a minus on a number."""
    if isinstance(expression, list):
        return [expression[0], *(_meant(part) for part in expression[1:])]
    if isinstance(expression, int) and not isinstance(expression, bool) and expression < 0:
        return ["-", -expression]
    return expression


def _same(text: str, expression: Expression) -> bool:
    """Whether Python reads the text as this condition; bools and ints told apart."""
    try:
        parsed = ast.parse(text, mode="eval").body
    except SyntaxError:
        return False
    return json.dumps(_read(parsed)) == json.dumps(_meant(expression))


def _written(expression: Expression) -> str:
    fork = Branch(expression=expression, taken=True, site=Site(file="m.py", line=5, col=7))
    record = InputRecord(args={"x": 1}, forks=(fork,), covered_lines=frozenset({5}))
    line = render_trace(record, COVERAGE).splitlines()[1]
    return line.removeprefix("fork m.py:5:7  ").removesuffix("  taken")


def _pairs(text: str) -> list[tuple[int, int]]:
    """Where each pair of parentheses opens and closes."""
    opened: list[int] = []
    pairs: list[tuple[int, int]] = []
    for at, character in enumerate(text):
        if character == "(":
            opened.append(at)
        elif character == ")":
            pairs.append((opened.pop(), at))
    return pairs


TREES = [_tree(random.Random(seed), 4) for seed in range(400)]


def test_python_reads_the_fork_line_as_the_condition() -> None:
    misread = [(tree, _written(tree)) for tree in TREES if not _same(_written(tree), tree)]

    assert misread == []


def _needless(expression: Expression) -> list[str]:
    """The fork line without each pair of parentheses Python reads the same condition without."""
    text = _written(expression)
    bare = [text[:start] + text[start + 1 : end] + text[end + 1 :] for start, end in _pairs(text)]
    return [line for line in bare if _same(line, expression)]


def test_each_pair_of_parentheses_is_one_python_needs() -> None:
    # without any one pair, Python reads another condition or none at all
    needless = [(_written(tree), _needless(tree)) for tree in TREES if _needless(tree)]

    assert needless == []
    # the trees hold parentheses to take away, so an empty answer is not an empty check
    assert sum(len(_pairs(_written(tree))) for tree in TREES) > 200
