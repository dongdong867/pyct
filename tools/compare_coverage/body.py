"""A target's own lines, read from its file by Python's parser: one rule for both sides.

The checker decides which lines belong to the target, not either side, so the two sides can
never disagree about it (decision own-lines-from-pythons-parser). The rule:

- ``NAME`` is the last top-level ``def``, ``async def`` or ``class`` of that name in the file.
  A top-level assignment or import after it that binds the name again is refused: a call
  would then run another object, and both sides would cover none of this body.
- Its own lines are the first line of every statement in its body, at every depth. A class
  body holds its methods.
- The ``def`` or ``class`` line, its decorators and its signature are not own lines: neither
  side runs them during a call. Nor is a leading docstring, for which Python compiles no code.
- A line inside a statement stands for the innermost statement that holds it, so a statement
  written over several lines counts once, at its first line.
"""

import ast
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

type Definition = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef

DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


class BodyError(Exception):
    """The file cannot be read or parsed, or has no top-level definition of the name."""


@dataclass(frozen=True)
class Body:
    """The target's own lines, and the own line every line inside its body stands for."""

    own_lines: frozenset[int]
    first_line: Mapping[int, int]

    def cut(self, lines: Iterable[int]) -> frozenset[int]:
        """The own lines that ``lines`` stand for. A line outside the body is dropped."""
        return frozenset(self.first_line[line] for line in lines if line in self.first_line)


def read_body(file: Path, name: str) -> Body:
    """The body of the top-level ``def`` or ``class`` named ``name`` in ``file``."""
    try:
        source = file.read_bytes()
    except OSError as error:
        raise BodyError(f"cannot read {file}: {error.strerror}") from error
    try:
        tree = ast.parse(source, filename=str(file))
    except SyntaxError as error:
        raise BodyError(f"{file} does not parse: {error.msg}, line {error.lineno}") from error
    definition = _definition(tree, name)
    if definition is None:
        raise BodyError(f"{file} has no top-level def or class named {name}")
    rebinding = _rebinding(tree, definition)
    if rebinding is not None:
        raise BodyError(f"{file} binds {name} again at line {rebinding}, after its def")
    return _body_of(definition)


def _definition(tree: ast.Module, name: str) -> Definition | None:
    """The last top-level definition of ``name``; a later one rebinds the name."""
    found = None
    for node in tree.body:
        if isinstance(node, DEFINITIONS) and node.name == name:
            found = node
    return found


def _rebinding(tree: ast.Module, definition: Definition) -> int | None:
    """The line of the first top-level assignment or import to bind the name after its def."""
    after = tree.body[tree.body.index(definition) + 1 :]
    for statement in after:
        if definition.name in _bound(statement):
            return statement.lineno
    return None


def _bound(statement: ast.stmt) -> set[str]:
    """The names a top-level assignment or import binds."""
    if isinstance(statement, ast.Import | ast.ImportFrom):
        return {alias.asname or alias.name.split(".")[0] for alias in statement.names}
    if isinstance(statement, ast.Assign):
        targets = statement.targets
    elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
        targets = [statement.target]
    else:
        return set()
    return {
        node.id for target in targets for node in ast.walk(target) if isinstance(node, ast.Name)
    }


def _body_of(definition: Definition) -> Body:
    """Map every line of every statement to its first line, outer statements first.

    An inner statement is mapped after the statement that holds it, so it overwrites the
    outer one's lines and each line ends up standing for the innermost statement.
    """
    first_line: dict[int, int] = {}
    own_lines: set[int] = set()
    for statement in _statements(definition):
        own_lines.add(statement.lineno)
        end = statement.end_lineno or statement.lineno
        for line in range(_start(statement), end + 1):
            first_line[line] = statement.lineno
    return Body(own_lines=frozenset(own_lines), first_line=first_line)


def _statements(node: ast.AST) -> Iterator[ast.stmt]:
    """Every statement nested in ``node``, each before the statements it holds."""
    for statement in _blocks(node):
        yield statement
        yield from _statements(statement)


def _blocks(node: ast.AST) -> list[ast.stmt]:
    """The statements directly inside ``node``: its bodies, its handlers' and its cases'."""
    statements: list[ast.stmt] = []
    for field in ("body", "orelse", "finalbody"):
        statements.extend(getattr(node, field, []))
    for clause in [*getattr(node, "handlers", []), *getattr(node, "cases", [])]:
        statements.extend(clause.body)
    if isinstance(node, DEFINITIONS) and ast.get_docstring(node, clean=False) is not None:
        statements.remove(node.body[0])
    return statements


def _start(statement: ast.stmt) -> int:
    """The statement's first line in the file: a decorated definition starts at a decorator."""
    decorators = getattr(statement, "decorator_list", [])
    return min([statement.lineno, *(decorator.lineno for decorator in decorators)])
