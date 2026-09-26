"""The size rules ruff has no rule for: function body lines and file lines.

The lint command runs it as ``python -m tests.line_limits src/ tests/``. A file is read the way
Python reads source, so a BOM or an encoding cookie is honored, and its lines are counted by
their line ends. A function's body runs from the line after its signature through its last
statement, blank lines and comments between included, less the lines of its docstring; a body
on the signature's own line is one line. A nested function counts toward the function that
holds it and is checked on its own as well.
"""

import ast
import bisect
import io
import sys
import tokenize
from collections.abc import Sequence
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
    try:
        with tokenize.open(path) as file:
            text = file.read()
    except (SyntaxError, UnicodeDecodeError) as error:
        return [Broken(path, 1, "syntax", f"cannot read the source: {error}")]
    broken = []
    lines = line_count(text)
    if lines > MAX_FILE_LINES:
        broken.append(Broken(path, 1, "file-lines", f"{lines} lines, at most {MAX_FILE_LINES}"))
    try:
        bodies = function_bodies(text, str(path))
    except SyntaxError as error:
        return [*broken, Broken(path, error.lineno or 1, "syntax", str(error.msg))]
    for function, length in bodies:
        if length > MAX_BODY_LINES:
            detail = f"{function.name} has {length} body lines, at most {MAX_BODY_LINES}"
            broken.append(Broken(path, function.lineno, "function-body-lines", detail))
    return broken


def line_count(text: str) -> int:
    """Each line end in ``text``, read with universal newlines, and a last line that has none."""
    return text.count("\n") + (1 if text and not text.endswith("\n") else 0)


def function_bodies(text: str, filename: str = "<source>") -> list[tuple[Function, int]]:
    """Every function in ``text`` and its body lines, counted as the module docstring says."""
    tree = ast.parse(text, filename=filename)
    colons = _outer_colons(text)
    bodies = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            # the signature ends at the first colon outside brackets after the `def`
            header_end, _ = colons[bisect.bisect(colons, (node.lineno, node.col_offset))]
            bodies.append((node, _body_lines(node, header_end)))
    return bodies


def _outer_colons(text: str) -> list[tuple[int, int]]:
    """Where each colon outside every bracket sits, in order; a signature ends at one."""
    depth = 0
    colons = []
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type != tokenize.OP:
            continue
        if token.string in ("(", "[", "{"):
            depth += 1
        elif token.string in (")", "]", "}"):
            depth -= 1
        elif token.string == ":" and depth == 0:
            colons.append(token.start)
    return colons


def _body_lines(function: Function, header_end: int) -> int:
    """The lines after the signature through the function's last, less the docstring's."""
    assert function.end_lineno is not None
    # a body written on the signature's own line starts there
    first = min(header_end + 1, function.body[0].lineno)
    lines = function.end_lineno - first + 1
    if ast.get_docstring(function, clean=False) is not None:
        docstring = function.body[0]
        assert docstring.end_lineno is not None
        lines -= docstring.end_lineno - max(docstring.lineno, first) + 1
    return lines


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
