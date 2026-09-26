"""A target's own lines, read from its compiled code: one rule for both sides.

The checker decides which lines belong to the target, not either side, so the two sides can
never disagree about it (decision own-lines-from-the-compiled-code). The rule:

- ``NAME`` is the last top-level ``def``, ``async def`` or ``class`` of that name in the file.
  A top-level assignment or import after it that binds the name again is refused: a call
  would then run another object, and both sides would cover none of this body.
- Its own lines are the lines its compiled code runs, read from the line table of its code
  object and of the code nested in it, such as an inner function. A line inside a statement
  that spans several lines stands for the innermost statement that holds it, as Python's
  parser reads the file, so such a statement counts once, at its first line.
- A code object starts on its ``def`` line or its first decorator, which a call does not run,
  so that line is left out. Python compiles no code for a docstring or for ``global`` and
  ``nonlocal``, so those lines are never own lines.
- A class's own lines are those of the functions its body defines, its methods, each without
  its starting line. The rest of the class body runs at import, as does a class nested in it,
  whose methods count the same way.
"""

import ast
import inspect
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import CodeType

type Definition = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef

DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


class BodyError(Exception):
    """The file cannot be read or parsed, or has no top-level definition of the name."""


@dataclass(frozen=True)
class Body:
    """The target's own lines, and the statement's first line every line in its body stands for."""

    own_lines: frozenset[int]
    first_line: Mapping[int, int]

    def cut(self, lines: Iterable[int]) -> frozenset[int]:
        """The own lines that ``lines`` stand for. Any other line is dropped."""
        stand_for = frozenset(self.first_line[line] for line in lines if line in self.first_line)
        return stand_for & self.own_lines


def read_body(file: Path, name: str) -> Body:
    """The body of the top-level ``def`` or ``class`` named ``name`` in ``file``."""
    tree = _parse(file)
    definition = _definition(tree, name)
    if definition is None:
        raise BodyError(f"{file} has no top-level def or class named {name}")
    rebinding = _rebinding(tree, definition)
    if rebinding is not None:
        raise BodyError(f"{file} binds {name} again at line {rebinding}, after its def")
    first_line = _first_lines(definition)
    code = _code_of(_compile(tree, file), definition)
    lines = _lines_run(code, isinstance(definition, ast.ClassDef))
    own_lines = frozenset(first_line[line] for line in lines if line in first_line)
    return Body(own_lines=own_lines, first_line=first_line)


def _parse(file: Path) -> ast.Module:
    try:
        source = file.read_bytes()
    except OSError as error:
        raise BodyError(f"cannot read {file}: {error.strerror}") from error
    try:
        return ast.parse(source, filename=str(file))
    except SyntaxError as error:
        raise BodyError(f"{file} does not parse: {error.msg}, line {error.lineno}") from error


def _compile(tree: ast.Module, file: Path) -> CodeType:
    try:
        return compile(tree, str(file), "exec")
    except SyntaxError as error:
        raise BodyError(f"{file} does not compile: {error.msg}, line {error.lineno}") from error


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


def _code_of(module: CodeType, definition: Definition) -> CodeType:
    """The code object the module compiles for ``definition``: its name, at its first line."""
    codes = {(code.co_name, code.co_firstlineno): code for code in _nested(module)}
    return codes[definition.name, _start(definition)]


def _lines_run(code: CodeType, is_class: bool) -> set[int]:
    """The lines a call runs in ``code``: all but its starting line, or a class's methods'."""
    if not is_class:
        return _lines(code) - {code.co_firstlineno}
    lines: set[int] = set()
    for nested in _nested(code):
        # a function's code runs in fresh locals; a class body's runs in the class namespace
        lines |= _lines_run(nested, is_class=not nested.co_flags & inspect.CO_OPTIMIZED)
    return lines


def _lines(code: CodeType) -> set[int]:
    """Every line in the line tables of ``code`` and the code nested in it."""
    lines = {line for _, _, line in code.co_lines() if line}
    for nested in _nested(code):
        lines |= _lines(nested)
    return lines


def _nested(code: CodeType) -> list[CodeType]:
    """The code objects ``code`` holds directly: its functions, classes and generators."""
    return [constant for constant in code.co_consts if isinstance(constant, CodeType)]


def _first_lines(definition: Definition) -> dict[int, int]:
    """Map every line of every statement in the body to its first line, outer statements first.

    An inner statement is mapped after the statement that holds it, so it overwrites the
    outer one's lines and each line ends up standing for the innermost statement.
    """
    first_line: dict[int, int] = {}
    for statement in _statements(definition):
        end = statement.end_lineno or statement.lineno
        for line in range(_start(statement), end + 1):
            first_line[line] = statement.lineno
    return first_line


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
    return statements


def _start(statement: ast.stmt) -> int:
    """The statement's first line in the file: a decorated definition starts at a decorator."""
    decorators = getattr(statement, "decorator_list", [])
    return min([statement.lineno, *(decorator.lineno for decorator in decorators)])
