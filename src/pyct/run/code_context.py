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
from collections.abc import Callable, Iterator

from pyct.intercept.hook import in_package
from pyct.run.target import Target

# the characters of code a request holds at most
CODE_LIMIT = 16_000

type Code = Callable[..., object]


def code_context(target: Target, limit: int = CODE_LIMIT) -> str:
    """The target's code, then its same-package callees', each headed by its module and name.

    The target's own code goes whole whatever its size. A callee whose code would take the
    whole past ``limit`` is left out, and the ones after it may still fit.
    """
    package = target.spec.partition("::")[0].partition(".")[0]
    waiting = deque(_starts(target))
    seen = {id(each) for each in waiting}
    parts: list[str] = []
    used = 0
    while waiting:
        function = waiting.popleft()
        part = _part(function)
        if part is None or (parts and used + len(part) + 2 > limit):
            continue
        parts.append(part)
        used += len(part) + 2
        for callee in _callees(function, part, package):
            if id(callee) not in seen:
                seen.add(id(callee))
                waiting.append(callee)
    return "\n\n".join(parts)


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
    tree = ast.parse(part.partition("\n")[2])
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        found = _resolved(node.func, function)
        if inspect.isclass(found):
            found = _function(found, "__init__")
        if inspect.isfunction(found) and in_package(package, found.__module__):
            yield found


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
