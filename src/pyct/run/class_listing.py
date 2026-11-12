"""The classes a seeds ask lists: each top-level class in the folder of the target's module, read
from its file with ``ast``, so no module is imported.

The target's own module comes first, then the folder's other modules by file name, but a
``__main__.py`` and a module that is not the user's own code (``user_module``), whose class an LLM
seed may not name. Each class goes under a ``# module::Name`` heading, the name a seed's
``"__class__"`` writes: its decorators and class line, its class-level annotated fields, such as
a dataclass's or a ``NamedTuple``'s, and its ``__init__``, each whole. A class goes in whole or
is left out, while the classes stay within the limit.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

from pyct.binding.libraries import library_module

# the characters the listed classes take at most, apart from the code's own limit
CLASS_LIMIT = 8_000
# the bytes of a file the listing reads at most; a larger file is skipped
FILE_LIMIT = 200_000
# the characters of the shortest class a module's part can show, apart from its module's name:
# the heading's ``# ``, ``::`` and one-letter name, a line break, and ``class A:``
SHORTEST_CLASS = len("# ::A\nclass A:")


@dataclass(frozen=True)
class ClassListing:
    """The text that lists the classes, empty when there are none, and the modules whose
    classes it lists."""

    text: str = ""
    modules: frozenset[str] = frozenset()


def class_listing(module_name: str, limit: int = CLASS_LIMIT) -> ClassListing:
    """The classes of the folder that holds the loaded module ``module_name``.

    A class that would take the text past ``limit`` is left out, and the
    ones after it may still fit. A module whose shortest possible class no
    longer fits is not read. A file that does not parse, that Python's
    parser cannot hold, that cannot be read, or that is larger than
    ``FILE_LIMIT`` is skipped. A module that is not loaded, or that has no
    file, lists nothing.
    """
    parts: list[str] = []
    modules: set[str] = set()
    used = 0
    for name, path in _folder_modules(module_name):
        if limit - used < SHORTEST_CLASS + len(name) or not user_module(name):
            continue
        for part in _class_parts(name, path):
            if used + len(part) > limit:
                continue
            parts.append(part)
            modules.add(name)
            used += len(part) + 2
    return ClassListing("\n\n".join(parts), frozenset(modules))


def user_module(name: str) -> bool:
    """Whether the module ``name`` is the user's own code, told before anything imports it:
    not ``__main__``, not one of pyct's own modules, and not a library's (``library_module``).
    The listing shows only such a module's classes, and an LLM seed builds only theirs
    (``ClassGate``)."""
    if name == "__main__" or name.partition(".")[0] == "pyct":
        return False
    return not library_module(name)


def _folder_modules(module_name: str) -> list[tuple[str, Path]]:
    """Each module of the folder that holds ``module_name``'s file, with its file: that module
    first, then the others by file name. For a package's ``__init__.py``, the folder is the
    package's, so the modules are the package's own."""
    file = getattr(sys.modules.get(module_name), "__file__", None)
    if not isinstance(file, str):
        return []
    own = Path(file)
    package = module_name if own.stem == "__init__" else module_name.rpartition(".")[0]
    others: list[tuple[str, Path]] = []
    for path in sorted(own.parent.glob("*.py")):
        name = _module_name(package, path.stem)
        if path.name != own.name and name is not None and path.is_file():
            others.append((name, path))
    return [(module_name, own), *others]


def _module_name(package: str, stem: str) -> str | None:
    """The module a file of ``package``'s folder is, or None when Python cannot import its name
    or it is a ``__main__.py``, which usually runs its program when imported: its
    ``__init__.py`` is the package itself."""
    if stem == "__init__":
        return package or None
    if stem == "__main__" or not stem.isidentifier():
        return None
    return f"{package}.{stem}" if package else stem


def _class_parts(module_name: str, path: Path) -> list[str]:
    """Each top-level class of the file, written as the listing shows it."""
    read = _read(path)
    if read is None:
        return []
    tree, lines = read
    return [
        _class_part(module_name, node, lines)
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    ]


def _read(path: Path) -> tuple[ast.Module, list[str]] | None:
    """The file's tree and its lines, or None for a file over ``FILE_LIMIT``, one that cannot be
    read, or one that does not parse, a parse too deep for Python's parser among them, which
    raises a RecursionError or a MemoryError."""
    try:
        if path.stat().st_size > FILE_LIMIT:
            return None
        source = importlib.util.decode_source(path.read_bytes())
        return ast.parse(source), source.splitlines()
    except (OSError, SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def _class_part(module_name: str, node: ast.ClassDef, lines: list[str]) -> str:
    """The class under its heading: its decorators and class line, then each class-level
    annotated field and its ``__init__``, in the order the class writes them."""
    header_end = max(node.lineno, _first_line(node.body[0]) - 1)
    header = lines[_first_line(node) - 1 : header_end]
    while header and not header[-1].strip():
        header.pop()
    shown = [
        "\n".join(lines[_first_line(each) - 1 : each.end_lineno or each.lineno])
        for each in node.body
        if isinstance(each, ast.AnnAssign)
        or (isinstance(each, ast.FunctionDef) and each.name == "__init__")
    ]
    return "\n".join([f"# {module_name}::{node.name}", *header, *shown])


def _first_line(node: ast.stmt) -> int:
    """The statement's first line: its first decorator's, for a decorated one."""
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno, *(each.lineno for each in decorators)])
