"""Function inspection — extracts target file and executable line range."""

from __future__ import annotations

import inspect
from collections.abc import Callable

from coverage import Coverage


def inspect_target(target: Callable) -> tuple[str, frozenset[int]]:
    """Return the target's source file and executable line numbers.

    Executable lines are the set of lines that coverage.py's static
    analyzer considers statements — comments, blank lines, and the
    ``def`` header itself are excluded. The result is used by the
    coverage tracker to decide when ``is_fully_covered()`` is true.

    Raises:
        TypeError: if ``target`` has no inspectable source (built-in
            or C extension function).
    """
    target_file = inspect.getfile(target)
    source_lines, start_line = inspect.getsourcelines(target)
    # Skip the ``def`` line — it lives inside the inspected range but the
    # tracer never fires on it (the def header is executed at import time
    # and does not emit a line event when the function body runs). Keeping
    # it in would make ``is_fully_covered()`` unreachable.
    func_range = set(range(start_line + 1, start_line + len(source_lines)))

    statements = _executable_statements(target_file)
    return target_file, frozenset(statements & func_range)


def _executable_statements(target_file: str) -> set[int]:
    """Return the set of executable line numbers in ``target_file``.

    Uses coverage.py's static analysis. Falls back to an empty set if
    the file cannot be analyzed — the caller will treat that as "no
    known executable lines," so ``is_fully_covered()`` stays false and
    exploration proceeds until it hits another termination condition.
    """
    try:
        cov = Coverage(data_file=None, include=[target_file])
        return set(cov.analysis(target_file)[1])
    except Exception:
        return set()
