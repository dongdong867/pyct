"""The code an LLM ask sends about a target: its own, then the functions it calls in its package.

The target comes first, and for a method its class's ``__init__``, then each function they call
that its package defines, breadth first, each once and whole, while the code stays within the
limit. A call is found by its name, read from the module the function was written in, or from
the class a method's ``self`` or ``cls`` names, without running any code of the target's.
"""

from __future__ import annotations

import ast
import inspect
import sys
import textwrap
from collections import deque
from collections.abc import Callable, Iterator, Mapping

from pyct.intercept.hook import in_package
from pyct.run.target import Target

# the characters of code a request holds at most
CODE_LIMIT = 16_000
# the lines of the function around a condition a request holds at most
AROUND_LINES = 200

type Code = Callable[..., object]

# the comments that mark a piece's first and last line in the code a summaries ask sends
MARK_START = "# >>> the loop"
MARK_END = "# <<< the loop"


def code_context(target: Target, limit: int = CODE_LIMIT) -> str:
    """The target's code, then its same-package callees', each headed by its module and name.

    The target's own code goes whole whatever its size. A callee whose code would take the
    whole past ``limit`` is left out, and the ones after it may still fit.
    """
    return _gathered(_starts(target), {}, _package(target), limit)


def code_with_piece(
    target: Target, file: str, lines: tuple[int, int], limit: int = CODE_LIMIT
) -> str:
    """The source of the innermost function in ``file`` that holds a piece's first and last
    ``lines``, dedented, the piece between a ``MARK_START`` and a ``MARK_END`` line; then, when
    its module is loaded and holds the function at its top level or in a class there, it is
    headed by its module and name, and its callees in the target's package follow, as
    ``code_context`` gives them. Empty when the file does not read or parse, or no function
    holds the piece."""
    read = _read(file)
    found = None if read is None else _innermost(read[1], lines[0])
    if read is None or found is None:
        return ""
    first, last = found
    written = read[0].splitlines()[first - 1 : last]
    start, end = lines[0] - first, lines[1] - first + 1
    indent = written[start][: len(written[start]) - len(written[start].lstrip())]
    written[end:end] = [f"{indent}{MARK_END}"]
    written[start:start] = [f"{indent}{MARK_START}"]
    marked = textwrap.dedent("\n".join(written))
    function = _function_at(file, first)
    if function is None:
        return marked
    head = f"# {function.__module__}.{function.__qualname__}\n{marked}"
    return _gathered([function], {id(function): head}, _package(target), limit)


def code_around(file: str, line: int, most: int = AROUND_LINES) -> str:
    """The source of the innermost function in ``file`` that holds ``line``, dedented, with no
    callee; the file's own lines when no function does. Past ``most`` lines, the ``most`` lines
    around ``line``. Empty when the file does not read or parse."""
    read = _read(file)
    if read is None:
        return ""
    lines = read[0].splitlines()
    start, end = _innermost(read[1], line) or (1, len(lines))
    if end - start + 1 > most:
        start = max(start, min(line - most // 2, end - most + 1))
        end = start + most - 1
    return textwrap.dedent("\n".join(lines[start - 1 : end]))


def _gathered(starts: list[Code], written: Mapping[int, str], package: str, limit: int) -> str:
    """The starts' code, then their callees' in ``package``, breadth first, each once, up to
    ``limit``; a function in ``written`` as written there."""
    waiting = deque(starts)
    seen = {id(each) for each in waiting}
    parts: list[str] = []
    used = 0
    while waiting:
        function = waiting.popleft()
        part = written.get(id(function)) or _part(function)
        if part is None or (parts and used + len(part) + 2 > limit):
            continue
        parts.append(part)
        used += len(part) + 2
        for callee in _callees(function, part, package):
            if id(callee) not in seen:
                seen.add(id(callee))
                waiting.append(callee)
    return "\n\n".join(parts)


def _package(target: Target) -> str:
    return target.spec.partition("::")[0].partition(".")[0]


def _read(file: str) -> tuple[str, ast.Module] | None:
    """The file's source and its tree, or None when it does not read or parse."""
    try:
        with open(file, encoding="utf-8") as opened:
            source = opened.read()
        return source, ast.parse(source, filename=file)
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def _innermost(tree: ast.Module, line: int) -> tuple[int, int] | None:
    """The first line, its first decorator's, and the last line of the innermost function that
    holds ``line``, or None when no function does."""
    found: tuple[int, int] | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            first = min([node.lineno, *(each.lineno for each in node.decorator_list)])
            last = node.end_lineno or node.lineno
            if first <= line <= last and (found is None or last - first < found[1] - found[0]):
                found = (first, last)
    return found


def _function_at(file: str, first: int) -> Code | None:
    """The function whose code starts at line ``first`` of ``file``, at the top level of the
    loaded module whose file it is or in a class there, read without running code; None when
    no module of that file is loaded or none holds it there."""
    for module in list(sys.modules.values()):
        if getattr(module, "__file__", None) != file:
            continue
        held = list(vars(module).values())
        held += [each for owner in held if inspect.isclass(owner) for each in vars(owner).values()]
        for each in held:
            found = each.__func__ if isinstance(each, staticmethod | classmethod) else each
            code = getattr(found, "__code__", None) if inspect.isfunction(found) else None
            if code is not None and (code.co_filename, code.co_firstlineno) == (file, first):
                return found
    return None


def _starts(target: Target) -> list[Code]:
    """The target, and for a method whose instance each input builds, its class's ``__init__``
    when the class defines one in Python."""
    starts: list[Code] = [target.fn]
    init = None if target.self_class is None else _function(target.self_class, "__init__")
    if init is not None:
        starts.append(init)
    return starts


def _part(function: Code) -> str | None:
    """The function's code, dedented, under a ``# module.qualname`` line. None when Python
    cannot give its source."""
    try:
        source = inspect.getsource(function)
    except (OSError, TypeError):
        return None
    name = f"{getattr(function, '__module__', '?')}.{getattr(function, '__qualname__', '?')}"
    return f"# {name}\n{textwrap.dedent(source).rstrip()}"


def _callees(function: Code, part: str, package: str) -> Iterator[Code]:
    """Each Python function the code calls by a name that leads to one the package defines; a
    class called leads to its ``__init__``."""
    tree = _parsed(part.partition("\n")[2])
    for node in () if tree is None else ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        found = _resolved(node.func, function)
        if inspect.isclass(found):
            found = _function(found, "__init__")
        module = getattr(found, "__module__", None)
        if inspect.isfunction(found) and isinstance(module, str) and in_package(package, module):
            yield found


def _parsed(code: str) -> ast.Module | None:
    """The code's tree, or None when Python cannot parse it alone. Code still indented, as a
    method whose string has a line at column 0 stays after dedenting, is read as a block."""
    try:
        return ast.parse(f"if 1:\n{code}" if code[:1].isspace() else code)
    except SyntaxError:
        return None


def _resolved(expression: ast.expr, function: Code) -> object:
    """What a call's name leads to: a bare name in the function's module, or ``self`` and
    ``cls`` as the function's class, then each attribute after it, read without running code.
    None when it leads nowhere pyct can read."""
    if isinstance(expression, ast.Name):
        if expression.id in ("self", "cls"):
            return _owner(function)
        return vars(_module(function)).get(expression.id)
    if isinstance(expression, ast.Attribute):
        base = _resolved(expression.value, function)
        if base is None:
            return None
        try:
            found = inspect.getattr_static(base, expression.attr)
        except AttributeError:
            return None
        return found.__func__ if isinstance(found, staticmethod | classmethod) else found
    return None


def _module(function: Code) -> object:
    """The module the function was written in, or an empty one when it is not loaded."""
    return sys.modules.get(getattr(function, "__module__", ""), _NOWHERE)


def _owner(function: Code) -> object:
    """The class a method was written in, read from its module by its qualified name."""
    owner: object = _module(function)
    for name in getattr(function, "__qualname__", "").split(".")[:-1]:
        owner = vars(owner).get(name) if hasattr(owner, "__dict__") else None
    return owner if inspect.isclass(owner) else None


def _function(cls: type, name: str) -> Code | None:
    """The Python function the class itself defines under ``name``, or None."""
    found = vars(cls).get(name)
    return found if inspect.isfunction(found) else None


class _Nowhere:
    """A module that holds no name."""


_NOWHERE = _Nowhere()
