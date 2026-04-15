"""Line tracer — records executed lines and enforces a per-call deadline."""

from __future__ import annotations

import sys
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from coverage import CoverageData


@contextmanager
def line_tracer(
    target_file: str,
    deadline: float | None = None,
) -> Iterator[set[int]]:
    """Install a ``sys.settrace`` line tracer scoped to ``target_file``.

    The yielded set is populated with line numbers as the target runs.
    When ``deadline`` is set and passed during tracing, raises
    ``TimeoutError`` from inside the traced frame — which unwinds back
    through the target's call stack and out of the ``with`` block.

    Cross-platform: ``sys.settrace`` works identically on Linux, macOS,
    and Windows, so this replaces SIGALRM-based timeout schemes. The
    previous tracer (if any, e.g. pytest-cov) is restored on exit.
    """
    hit_lines: set[int] = set()

    def tracer(frame, event, arg):  # noqa: ARG001
        if event == "line":
            if frame.f_code.co_filename == target_file:
                hit_lines.add(frame.f_lineno)
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError("target exceeded soft timeout")
        return tracer

    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        yield hit_lines
    finally:
        sys.settrace(previous)


def lines_to_coverage_data(target_file: str, lines: set[int]) -> CoverageData:
    """Wrap a set of executed lines in a ``CoverageData`` object.

    The coverage tracker's ``update()`` method reads ``data.lines(file)``,
    so we construct a throw-away on-disk data file and populate it. The
    basename is a unique temp path so concurrent runs don't collide.
    """
    temp_dir = tempfile.gettempdir()
    suffix = uuid.uuid4().hex[:8]
    data = CoverageData(basename=f"{temp_dir}/.pyct-cov.{suffix}")
    if lines:
        data.add_lines({target_file: sorted(lines)})
    return data
