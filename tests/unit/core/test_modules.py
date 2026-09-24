"""How core's modules depend on each other."""

import ast
import importlib.util
from pathlib import Path

import pytest

import pyct.core

CORE = "pyct.core"
CORE_DIR = Path(pyct.core.__file__).parent


def _underscored(name: str) -> bool:
    """Whether a name is private: a leading underscore, and not a dunder every module has."""
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def _resolved(node: ast.ImportFrom) -> str:
    """The full module name an import reads from."""
    # core's modules sit directly in the core package, so a relative import resolves against
    # it; an absolute one comes back unchanged
    return importlib.util.resolve_name("." * node.level + (node.module or ""), CORE)


def _dotted(node: ast.expr) -> str | None:
    """The dotted name a chain of attributes on a name spells, like pyct.core.ints, or None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and (base := _dotted(node.value)) is not None:
        return f"{base}.{node.attr}"
    return None


def _core_modules_bound(tree: ast.Module) -> dict[str, str]:
    """Each local name the source binds to a whole core module, and that module's full name."""
    bound: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            # without `as`, the code reads the module through its full dotted name
            for alias in node.names:
                if alias.name.startswith(f"{CORE}."):
                    bound[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and _resolved(node) == CORE:
            # only an import from the package binds a module; one from a module inside it,
            # like pyct.core.bools, binds a name in that module
            for alias in node.names:
                bound[alias.asname or alias.name] = f"{CORE}.{alias.name}"
    return bound


def _underscored_imports(tree: ast.Module) -> list[str]:
    """Each underscored name an import takes straight from a core module."""
    return [
        f"{module}.{alias.name}"
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (module := _resolved(node)).startswith(CORE)
        for alias in node.names
        if _underscored(alias.name)
    ]


def _underscored_attributes(tree: ast.Module) -> list[str]:
    """Each underscored attribute read off a name the source bound to a whole core module."""
    bound = _core_modules_bound(tree)
    return [
        f"{bound[dotted]}.{node.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and _underscored(node.attr)
        if (dotted := _dotted(node.value)) is not None and dotted in bound
    ]


def _underscored_reaches(source: str) -> list[str]:
    """Every underscored name the source takes from a core module, as module.name."""
    tree = ast.parse(source)
    return _underscored_imports(tree) + _underscored_attributes(tree)


def test_no_core_module_imports_another_modules_underscored_name() -> None:
    # an underscored name is its own module's business; a core module that needs one from
    # another is a sign the name belongs in the shared module, public
    reached_in = {
        path.name: names
        for path in sorted(CORE_DIR.glob("*.py"))
        if (names := _underscored_reaches(path.read_text()))
    }

    assert reached_in == {}


# each way a module can reach ints' underscored _operand, as the source that does it
SIDE_DOORS: dict[str, str] = {
    "from-import": "from pyct.core.ints import _operand",
    "relative-from-import": "from .ints import _operand",
    "module-then-attribute": "from pyct.core import ints\nints._operand",
    "relative-module-then-attribute": "from . import ints\nints._operand",
    "aliased-import": "import pyct.core.ints as ints\nints._operand",
    "dotted-import": "import pyct.core.ints\npyct.core.ints._operand",
}

# sources that reach nothing private in core: a public name, a dunder every module has, a
# receiver's own attribute, and an underscored name from outside core
NOTHING_PRIVATE: dict[str, str] = {
    "public-from-import": "from pyct.core.values import own",
    "public-attribute": "from pyct.core import values\nvalues.own",
    "dunder-attribute": "from pyct.core import ints\nints.__file__",
    "own-attribute": "self._sink",
    "outside-core": "from os import _exit",
}


@pytest.mark.parametrize("source", SIDE_DOORS.values(), ids=list(SIDE_DOORS))
def test_the_guard_sees_every_way_to_reach_an_underscored_name(source: str) -> None:
    assert _underscored_reaches(source) == ["pyct.core.ints._operand"]


@pytest.mark.parametrize("source", NOTHING_PRIVATE.values(), ids=list(NOTHING_PRIVATE))
def test_the_guard_leaves_public_names_and_dunders_alone(source: str) -> None:
    assert _underscored_reaches(source) == []
