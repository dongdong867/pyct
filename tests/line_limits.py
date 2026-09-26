"""The size rules ruff has no rule for: function body lines and file lines.

The lint command runs it as ``python -m tests.line_limits src/ tests/``. A
function's body runs from its first statement after the docstring to its last
line, blank lines and comments included, so documenting a function never
pushes it over. A nested function counts toward the function that holds it
and is checked on its own as well. A file counts every line.
"""

import ast
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

MAX_BODY_LINES = 30
MAX_FILE_LINES = 499

USAGE = "usage: python -m tests.line_limits PATH [PATH ...]"

type Function = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True)
class Broken:
    """One rule a file breaks, printed the way ruff prints a finding."""

    path: Path
    line: int
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule} {self.detail}"


def check_file(path: Path) -> list[Broken]:
    """Every rule the file at ``path`` breaks, the file's own length first."""
    text = path.read_text(encoding="utf-8")
    broken = []
    lines = len(text.splitlines())
    if lines > MAX_FILE_LINES:
        broken.append(Broken(path, 1, "file-lines", f"{lines} lines, at most {MAX_FILE_LINES}"))
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as error:
        return [*broken, Broken(path, error.lineno or 1, "syntax", str(error.msg))]
    return [*broken, *_long_bodies(path, tree)]


def _long_bodies(path: Path, tree: ast.Module) -> Iterator[Broken]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            lines = body_lines(node)
            if lines > MAX_BODY_LINES:
                detail = f"{node.name} has {lines} body lines, at most {MAX_BODY_LINES}"
                yield Broken(path, node.lineno, "function-body-lines", detail)


def body_lines(function: Function) -> int:
    """How many lines the body spans after the docstring; 0 when nothing follows it."""
    body = function.body
    if ast.get_docstring(function, clean=False) is not None:
        body = body[1:]
    if not body or function.end_lineno is None:
        return 0
    return function.end_lineno - body[0].lineno + 1


def python_files(roots: Sequence[Path]) -> list[Path]:
    """Each root that is a file, and every ``.py`` file under each root that is a directory."""
    files = []
    for root in roots:
        files.extend([root] if root.is_file() else sorted(root.rglob("*.py")))
    return files


def main(argv: Sequence[str] | None = None) -> int:
    """Print every rule broken under the given paths. 0: none broken, 1: some, 2: usage."""
    roots = [Path(arg) for arg in (sys.argv[1:] if argv is None else argv)]
    if not roots:
        print(USAGE, file=sys.stderr)
        return 2
    for root in roots:
        if not root.exists():
            print(f"line_limits: no such file or directory: {root}", file=sys.stderr)
            return 2
    files = python_files(roots)
    broken = [each for path in files for each in check_file(path)]
    for each in broken:
        print(each)
    checked = f"{len(files)} file" if len(files) == 1 else f"{len(files)} files"
    print(f"Line limits: {checked} checked, {len(broken)} broken.")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
