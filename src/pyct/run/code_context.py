"""The code an LLM ask sends about a target: its own, then the functions it calls in its package.

The target comes first, and for a method its class's ``__init__``, then each function they call
that its package defines, breadth first, each once and whole, while the code stays within the
limit. A call is found by its name, read from the module the function was written in, or from
the class a method's ``self`` or ``cls`` names, and followed through ``__wrapped__`` to the
function a decorator such as ``functools.lru_cache`` wraps. Each module, class and wrapper it
reads to find a call is read by its type alone. The code itself is read by ``inspect.getsource``, as ``_part``
says, which reads attributes as Python does.
"""

from __future__ import annotations

import ast
import inspect
import sys
import textwrap
import types
from collections import deque
from collections.abc import Callable, Iterator, Mapping
from typing import TypeGuard

from pyct.intercept.hook import in_package
from pyct.results.source_files import SourceFiles, read_source
from pyct.run.namespaces import file_of, namespace
from pyct.run.target import Target

# the characters of code a request holds at most
CODE_LIMIT = 16_000
# the lines of the function around a condition a request holds at most
AROUND_LINES = 200
# the ``__wrapped__`` steps followed from a called name at most, the count ``core`` follows
_WRAPPED_STEPS = 8

type Code = Callable[..., object]

# the members that hold the function a static and a class method wrap, read by ``staticmethod``
# and ``classmethod`` themselves, whatever the subclass of the wrapper they read
_STATIC_FUNC = vars(staticmethod)["__func__"]
_CLASS_FUNC = vars(classmethod)["__func__"]

# the comments that mark a loop's first and last line in the code a summaries ask sends
MARK_START = "# >>> the loop"
MARK_END = "# <<< the loop"


def marks(word: str) -> tuple[str, str]:
    """The comments that mark the first and last line of a piece the ``word`` names, ``loop`` or
    ``call``, in the code a summaries ask sends."""
    return f"# >>> the {word}", f"# <<< the {word}"


def code_context(target: Target, limit: int = CODE_LIMIT) -> str:
    """The target's code, then its same-package callees', each headed by its module and name.

    The target's own code goes whole whatever its size. A callee whose code would take the
    whole past ``limit`` is left out, and the ones after it may still fit.
    """
    return _gathered(_starts(target), {}, _package(target), limit)


def code_with_piece(
    target: Target,
    file: str,
    lines: tuple[int, int],
    word: str = "loop",
    files: SourceFiles | None = None,
) -> str:
    """The source of the innermost function in ``file`` that holds a piece's first and last
    ``lines``, dedented, the piece between the two lines ``marks(word)`` gives; then, when
    its module is loaded and holds the function at its top level or in a class there, it is
    headed by its module and name, and its callees in the target's package follow, as
    ``code_context`` gives them, within ``CODE_LIMIT``. The file is read through the run's
    ``files``. Empty when the file does not read or parse, or no function holds the piece."""
    read = (files or SourceFiles()).read(file)
    found = None if read is None else _innermost(read[1], lines[0])
    if read is None or found is None:
        return ""
    first, last = found
    written = read[0].splitlines()[first - 1 : last]
    start, end = lines[0] - first, lines[1] - first + 1
    indent = written[start][: len(written[start]) - len(written[start].lstrip())]
    above, below = marks(word)
    written[end:end] = [f"{indent}{below}"]
    written[start:start] = [f"{indent}{above}"]
    marked = textwrap.dedent("\n".join(written))
    function = _function_at(file, first)
    if function is None:
        return marked
    head = f"# {function.__module__}.{function.__qualname__}\n{marked}"
    return _gathered([function], {id(function): head}, _package(target), CODE_LIMIT)


def function_code(file: str, first: int, head: str, files: SourceFiles | None = None) -> str | None:
    """The source of the function in ``file`` whose code starts at line ``first``, its first
    decorator's when it has one, dedented, under a ``# head`` line; None when the file does not
    read or parse, or no function starts there. The file is read through the run's ``files``."""
    read = (files or SourceFiles()).read(file)
    if read is None:
        return None
    for node in ast.walk(read[1]):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        start = min([node.lineno, *(each.lineno for each in node.decorator_list)])
        if start == first:
            written = "\n".join(read[0].splitlines()[start - 1 : node.end_lineno])
            return f"# {head}\n{textwrap.dedent(written).rstrip()}"
    return None


def code_around(file: str, line: int, most: int = AROUND_LINES) -> str:
    """The source of the innermost function in ``file`` that holds ``line``, dedented, with no
    callee; the file's own lines when no function does. Past ``most`` lines, the ``most`` lines
    around ``line``. Empty when the file does not read or parse."""
    read = read_source(file)
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
    seen = {id(each) for each in waiting} | {id(_followed(each)) for each in waiting}
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
        if file_of(module) != file:
            continue
        held = list(namespace(module).values())
        held += [each for owner in held if _is_class(owner) for each in namespace(owner).values()]
        for each in held:
            found = _unwrapped(each)
            if not _is_function(found):
                continue
            if (found.__code__.co_filename, found.__code__.co_firstlineno) == (file, first):
                return found
    return None


def _is_class(value: object) -> TypeGuard[type]:
    """Whether the value is a class, read by its type alone: ``isinstance`` would read its
    ``__class__``, which a lazy object of the target's answers by running its setup."""
    return issubclass(type(value), type)


def _is_function(value: object) -> TypeGuard[types.FunctionType]:
    """Whether the value is a Python function, read by its type alone."""
    return type(value) is types.FunctionType


def _unwrapped(value: object) -> object:
    """The function a static or class method wraps, read by its type alone, through the member
    ``staticmethod`` or ``classmethod`` defines, so that no attribute hook of a subclass runs;
    else the value."""
    if issubclass(type(value), staticmethod):
        return _STATIC_FUNC.__get__(value)
    if issubclass(type(value), classmethod):
        return _CLASS_FUNC.__get__(value)
    return value


def _followed(value: object) -> object:
    """What the value's ``__wrapped__`` chain ends at, at most ``_WRAPPED_STEPS`` steps, each
    read with ``inspect.getattr_static`` so that no attribute hook of a wrapper runs; the
    value itself when it has none."""
    for _ in range(_WRAPPED_STEPS):
        try:
            value = inspect.getattr_static(value, "__wrapped__")
        except AttributeError:
            break
    return value


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
    cannot give its source. ``inspect.getsource`` and the ``# module.qualname`` line read the
    function's attributes, and the ``__dict__`` of the ``sys.modules`` entry its ``__module__``
    names, as Python reads them, so an attribute hook of that entry's class runs, and so does an
    attribute hook of the target's own callable when it is not a plain function."""
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
        if _is_class(found):
            found = _function(found, "__init__")
        found = _followed(found)
        if not _is_function(found):
            continue
        module = found.__module__
        if issubclass(type(module), str) and in_package(package, module):
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
        return namespace(_module(function)).get(expression.id)
    if isinstance(expression, ast.Attribute):
        base = _resolved(expression.value, function)
        if base is None:
            return None
        try:
            found = inspect.getattr_static(base, expression.attr)
        except AttributeError:
            return None
        return _unwrapped(found)
    return None


def _module(function: Code) -> object:
    """The entry of ``sys.modules`` the function names as its module, or None."""
    return sys.modules.get(getattr(function, "__module__", ""))


def _owner(function: Code) -> object:
    """The class a method was written in, read from its module by its qualified name."""
    owner: object = _module(function)
    for name in getattr(function, "__qualname__", "").split(".")[:-1]:
        owner = namespace(owner).get(name)
    return owner if _is_class(owner) else None


def _function(cls: type, name: str) -> Code | None:
    """The Python function the class itself defines under ``name``, or None."""
    found = namespace(cls).get(name)
    return found if _is_function(found) else None
