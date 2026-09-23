"""How core's modules depend on each other."""

import ast
from pathlib import Path

import pyct.core

CORE_DIR = Path(pyct.core.__file__).parent


def _underscored_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    return [
        f"{node.module}.{alias.name}"
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("pyct.core")
        for alias in node.names
        if alias.name.startswith("_")
    ]


def test_no_core_module_imports_another_modules_underscored_name() -> None:
    # an underscored name is its own module's business; a core module that needs one from
    # another is a sign the name belongs in the shared module, public
    reached_in = {
        path.name: names
        for path in sorted(CORE_DIR.glob("*.py"))
        if (names := _underscored_imports(path))
    }

    assert reached_in == {}
