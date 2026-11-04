"""How core's modules depend on each other."""

import ast
import importlib.util
from pathlib import Path

import pytest

import pyct.core

CORE = "pyct.core"
CORE_DIR = Path(pyct.core.__file__).parent
# the package the samples below are read in: the folder ints sits in
SAMPLE_PACKAGE = f"{CORE}.numbers"


def _underscored(name: str) -> bool:
    """Whether a name is private: a leading underscore, and not a dunder every module has."""
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def _package(path: Path) -> str:
    """The package a file of core sits in: core, or one of its folders."""
    return ".".join([CORE, *path.parent.relative_to(CORE_DIR).parts])


def _module(path: Path) -> str:
    """The full name of a file of core: core itself, a folder, or a module."""
    parts = path.relative_to(CORE_DIR).with_suffix("").parts
    return ".".join([CORE, *(parts[:-1] if parts[-1] == "__init__" else parts)])


# every module and folder of core, by its full name
MODULES = {_module(path) for path in CORE_DIR.rglob("*.py")}


def _resolved(node: ast.ImportFrom, package: str) -> str:
    """The full module name an import reads from."""
    # a relative import resolves against the package of the file it sits in; an absolute one
    # comes back unchanged
    return importlib.util.resolve_name("." * node.level + (node.module or ""), package)


def _dotted(node: ast.expr) -> str | None:
    """The dotted name a chain of attributes on a name spells, like pyct.core.numbers.ints, or
    None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and (base := _dotted(node.value)) is not None:
        return f"{base}.{node.attr}"
    return None


def _names_bound(tree: ast.Module, package: str) -> dict[str, str]:
    """Each local name an import binds, and the full name it stands for."""
    bound: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # without `as`, an import binds its first name, and the code reads the rest
                root = alias.name.partition(".")[0]
                bound[alias.asname or root] = alias.name if alias.asname else root
        elif isinstance(node, ast.ImportFrom):
            module = _resolved(node, package)
            for alias in node.names:
                bound[alias.asname or alias.name] = f"{module}.{alias.name}"
    return bound


def _underscored_imports(tree: ast.Module, package: str) -> list[str]:
    """Each underscored name an import takes straight from a core module."""
    return [
        f"{module}.{alias.name}"
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and (module := _resolved(node, package)).startswith(CORE)
        for alias in node.names
        if _underscored(alias.name)
    ]


def _full_name(dotted: str, bound: dict[str, str]) -> str | None:
    """The full name a dotted chain spells when it starts with a name an import bound, like
    pyct.core.numbers.ints for numbers.ints after `from pyct.core import numbers`; None when it
    starts with none."""
    parts = dotted.split(".")
    for end in range(len(parts), 0, -1):
        if (head := ".".join(parts[:end])) in bound:
            return ".".join([bound[head], *parts[end:]])
    return None


def _underscored_attributes(tree: ast.Module, package: str) -> list[str]:
    """Each underscored attribute read off a chain that spells a core module or folder."""
    bound = _names_bound(tree, package)
    return [
        f"{full}.{node.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and _underscored(node.attr)
        if (dotted := _dotted(node.value)) is not None
        and (full := _full_name(dotted, bound)) in MODULES
    ]


def _underscored_reaches(source: str, package: str) -> list[str]:
    """The underscored core names the source, read in ``package``, reaches through the import
    shapes read here."""
    tree = ast.parse(source)
    return _underscored_imports(tree, package) + _underscored_attributes(tree, package)


def test_no_core_module_imports_another_modules_underscored_name() -> None:
    # an underscored name is its own module's business; a core module that needs one from
    # another is a sign the name belongs in the shared module, public
    reached_in = {
        path.relative_to(CORE_DIR).as_posix(): names
        for path in sorted(CORE_DIR.rglob("*.py"))
        if (names := _underscored_reaches(path.read_text(), _package(path)))
    }

    assert reached_in == {}


# one sample per import shape the guard reads, each reaching ints' underscored _operand;
# any other way in passes the guard
SIDE_DOORS: dict[str, str] = {
    "from-import": "from pyct.core.numbers.ints import _operand",
    "relative-from-import": "from .ints import _operand",
    "module-then-attribute": "from pyct.core.numbers import ints\nints._operand",
    "relative-module-then-attribute": "from . import ints\nints._operand",
    "aliased-import": "import pyct.core.numbers.ints as ints\nints._operand",
    "dotted-import": "import pyct.core.numbers.ints\npyct.core.numbers.ints._operand",
    "folder-then-module-attribute": "from pyct.core import numbers\nnumbers.ints._operand",
    "relative-folder-then-module-attribute": "from .. import numbers\nnumbers.ints._operand",
    "dotted-folder-import": "import pyct.core.numbers\npyct.core.numbers.ints._operand",
    "chain-from-the-root": "import pyct.core.numbers.floats\npyct.core.numbers.ints._operand",
    "core-then-chain": "from pyct import core\ncore.numbers.ints._operand",
}

# sources that reach nothing private in core: a public name, a dunder every module has, a
# receiver's own attribute, and an underscored name from outside core
NOTHING_PRIVATE: dict[str, str] = {
    "public-from-import": "from pyct.core.foundation.values import own",
    "public-attribute": "from pyct.core.foundation import values\nvalues.own",
    "dunder-attribute": "from pyct.core.numbers import ints\nints.__file__",
    "own-attribute": "self._sink",
    "public-object-attribute": "from pyct.core.foundation import spans\nspans.EMPTY._replace()",
    "outside-core": "from os import _exit",
}


@pytest.mark.parametrize("source", SIDE_DOORS.values(), ids=list(SIDE_DOORS))
def test_the_guard_sees_each_side_door(source: str) -> None:
    assert _underscored_reaches(source, SAMPLE_PACKAGE) == ["pyct.core.numbers.ints._operand"]


@pytest.mark.parametrize("source", NOTHING_PRIVATE.values(), ids=list(NOTHING_PRIVATE))
def test_the_guard_leaves_public_names_and_dunders_alone(source: str) -> None:
    assert _underscored_reaches(source, SAMPLE_PACKAGE) == []
