"""Function inspection — extracts target file and executable line range."""

from __future__ import annotations

import inspect
from collections.abc import Callable

from coverage import Coverage


def inspect_target(target: Callable) -> tuple[str, frozenset[int], int]:
    """Return the target's source file, executable lines, and def-line number.

    Executable lines are the set of lines that coverage.py's static
    analyzer considers statements within the function's source range.
    The returned set INCLUDES the ``def`` header line to match legacy's
    line-counting convention (legacy pre-covers the def line at init so
    it counts toward both total and executed). Callers should pass the
    third return value to ``CoverageTracker(..., pre_covered={def_line})``
    so ``is_fully_covered()`` doesn't get stuck on the def line, which
    never fires during function-body execution.

    Raises:
        TypeError: if ``target`` has no inspectable source (built-in
            or C extension function).
    """
    unwrapped = inspect.unwrap(target)
    target_file = inspect.getfile(unwrapped)
    source_lines, start_line = inspect.getsourcelines(unwrapped)
    func_range = set(range(start_line, start_line + len(source_lines)))

    statements = _executable_statements(target_file)
    return target_file, frozenset(statements & func_range), start_line


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
