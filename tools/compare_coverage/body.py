"""A target's own lines, read from its compiled code: one rule for both sides.

The checker decides which lines belong to the target, not either side, so the two sides can
never disagree about it (decision own-lines-from-the-compiled-code). The rule:

- ``NAME`` is the last top-level ``def``, ``async def`` or ``class`` of that name in the file.
  Module-level code after it that binds or deletes the name is refused: a call would then
  run another object, and both sides would cover none of this body. The check reads the
  statements after the def and the blocks of their ``if``, ``for``, ``while``, ``with``,
  ``try`` and ``match``: an assignment of any kind, a ``for``, ``with``, ``except`` or
  ``match`` target, ``del``, an import, or a ``def`` or ``class`` of the name. It does not
  read inside functions, classes, lambdas or comprehensions. ``NAME = wrap(NAME)``, a call
  of another function that takes ``NAME`` as an argument, wraps the target as a decorator
  does and is kept. An ``import *`` after the def is refused, since the file cannot show
  whether it binds the name.
- Its own lines are the lines its compiled code runs, read from the line table of its code
  object and of the code nested in it, such as an inner function. A line inside a statement
  that spans several lines stands for the innermost statement that holds it, as Python's
  parser reads the file, so such a statement counts once, at its first line.
- A code object starts on its ``def`` line or its first decorator, which a call does not run,
  so that line is left out. Python compiles no code for a docstring or for ``global`` and
  ``nonlocal``, so those lines are never own lines.
- A class's own lines are those of the functions its body defines, its methods, each without
  its starting line, in the class body's blocks too. The rest of the class body runs at
  import, a lambda or generator in a class-level assignment among it; a class nested in it
  counts its own methods the same way.
"""

import ast
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import CodeType

type Definition = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef

DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

# what binds names of its own rather than the module's
SCOPES = (*DEFINITIONS, ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)

# what binds the name its ``name`` field holds
BINDERS = (*DEFINITIONS, ast.ExceptHandler, ast.MatchAs, ast.MatchStar)


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
        raise BodyError(f"{file} {rebinding}")
    first_line = _first_lines(definition)
    lines = _lines_run(definition, _codes(_compile(tree, file)), file)
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


def _rebinding(tree: ast.Module, definition: Definition) -> str | None:
    """How the module binds the name again after its def, or ``None`` when it does not."""
    name = definition.name
    for statement in tree.body[tree.body.index(definition) + 1 :]:
        for node in _module_level(statement, name):
            if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
                return f"imports * at line {node.lineno}, after the def of {name}"
            if _binds(node, name):
                line = getattr(node, "lineno", statement.lineno)
                return f"binds {name} again at line {line}, after its def"
    return None


def _module_level(node: ast.AST, name: str) -> Iterator[ast.AST]:
    """``node`` and what it holds that runs in the module's scope.

    The insides of a function, class, lambda or comprehension bind their own names, so the
    walk stops at them, as it does at the targets of a wrap and of an annotation alone.
    """
    yield node
    if isinstance(node, SCOPES):
        return
    if isinstance(node, ast.Assign) and _wraps(node, name):
        children: list[ast.AST] = [node.value]
    elif isinstance(node, ast.AnnAssign) and node.value is None:
        children = [node.annotation]
    else:
        children = list(ast.iter_child_nodes(node))
    for child in children:
        yield from _module_level(child, name)


def _binds(node: ast.AST, name: str) -> bool:
    """True when ``node`` binds ``name`` or deletes it."""
    if isinstance(node, ast.Name):
        return node.id == name and isinstance(node.ctx, ast.Store | ast.Del)
    if isinstance(node, ast.Import | ast.ImportFrom):
        return name in {alias.asname or alias.name.split(".")[0] for alias in node.names}
    if isinstance(node, ast.MatchMapping):
        return node.rest == name
    bound = getattr(node, "name", None)
    return isinstance(node, BINDERS) and bound == name


def _wraps(assign: ast.Assign, name: str) -> bool:
    """True for ``name = wrap(name)``: a call of another function that takes ``name`` itself."""
    call = assign.value
    alone = all(isinstance(target, ast.Name) for target in assign.targets)
    if not alone or not isinstance(call, ast.Call) or _is_name(call.func, name):
        return False
    return any(_is_name(value, name) for value in [*call.args, *(k.value for k in call.keywords)])


def _is_name(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _codes(code: CodeType) -> dict[tuple[str, int], CodeType]:
    """Every code object nested in ``code``, at any depth, by its name and its first line.

    A generic ``def f[T]`` or ``class C[T]`` compiles inside a scope for its type
    parameters, so its code sits one level below the module's own.
    """
    codes: dict[tuple[str, int], CodeType] = {}
    for nested in _nested(code):
        codes[nested.co_name, nested.co_firstlineno] = nested
        codes |= _codes(nested)
    return codes


def _find(
    codes: Mapping[tuple[str, int], CodeType], definition: Definition, file: Path
) -> CodeType:
    """The code object compiled for ``definition``: its name, at its first line."""
    code = codes.get((definition.name, _start(definition)))
    if code is None:
        line = _start(definition)
        raise BodyError(f"{file} compiles no code for {definition.name} at line {line}")
    return code


def _lines_run(
    definition: Definition, codes: Mapping[tuple[str, int], CodeType], file: Path
) -> set[int]:
    """The lines a call runs: all a function's code holds but its starting line.

    A class's are those of the functions and classes its body defines, in its blocks too:
    the rest of the body, lambdas and generators in its assignments among it, runs at import.
    """
    if not isinstance(definition, ast.ClassDef):
        code = _find(codes, definition, file)
        return _lines(code) - {code.co_firstlineno}
    lines: set[int] = set()
    for member in _members(definition):
        lines |= _lines_run(member, codes, file)
    return lines


def _members(node: ast.AST) -> Iterator[Definition]:
    """The defs and classes a class body holds, in its blocks too, and not inside them."""
    for statement in _blocks(node):
        if isinstance(statement, DEFINITIONS):
            yield statement
        else:
            yield from _members(statement)


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
