"""Line tracer — records executed lines per-file and enforces a deadline."""

from __future__ import annotations

import sys
import tempfile
import time
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager

from coverage import CoverageData


@contextmanager
def line_tracer(
    target_files: Iterable[str],
    deadline: float | None = None,
) -> Iterator[dict[str, set[int]]]:
    """Install a ``sys.settrace`` line tracer scoped to ``target_files``.

    The yielded dict has one entry per file in ``target_files``; values
    are populated with line numbers as the target runs. Events from
    files outside the scope (Python stdlib, unrelated modules,
    pytest internals) are silently ignored — keeps the output
    focused and the per-event cost bounded.

    When ``deadline`` is set and passed during tracing, raises
    ``TimeoutError`` from inside the traced frame — which unwinds back
    through the target's call stack and out of the ``with`` block.

    Cross-platform: ``sys.settrace`` works identically on Linux, macOS,
    and Windows, so this replaces SIGALRM-based timeout schemes. The
    previous tracer (if any, e.g. pytest-cov) is restored on exit.
    """
    scope = frozenset(target_files)
    hits: dict[str, set[int]] = {f: set() for f in scope}

    def tracer(frame, event, arg):  # noqa: ARG001
        if event == "line":
            filename = frame.f_code.co_filename
            if filename in scope:
                hits[filename].add(frame.f_lineno)
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError("target exceeded soft timeout")
        return tracer

    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        yield hits
    finally:
        sys.settrace(previous)


def lines_to_coverage_data(per_file_lines: dict[str, set[int]]) -> CoverageData:
    """Wrap per-file executed-line sets in a ``CoverageData`` object.

    The coverage tracker's ``update()`` method reads ``data.lines(file)``,
    so we construct a throw-away on-disk data file and populate it.
    The basename is a unique temp path so concurrent runs don't collide.
    Files with empty line sets are skipped — coverage.py treats a file
    with an explicitly-empty ``lines()`` differently from a file that
    was never added, and the tracker's update path is no-op either way.
    """
    temp_dir = tempfile.gettempdir()
    suffix = uuid.uuid4().hex[:8]
    data = CoverageData(basename=f"{temp_dir}/.pyct-cov.{suffix}")
    non_empty = {f: sorted(lines) for f, lines in per_file_lines.items() if lines}
    if non_empty:
        data.add_lines(non_empty)
    return data
