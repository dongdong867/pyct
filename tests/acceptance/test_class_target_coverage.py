"""Regression tests for class-target coverage reporting.

Benchmark runners ``llm_only`` and ``concolic_llm`` must report identical
coverage when both execute a class target with a trivial ``__init__``.
Before the fix, the engine injected the class header line into
``executed_lines`` via ``pre_covered``, which shadowed the first
body-line anchor that ``_build_coverage_result`` uses for its
def-header backfill. The result: ``concolic_llm`` undercounted by the
number of headers between the class line and the first body line
(typically the ``def __init__`` line).
"""

from __future__ import annotations

import inspect

from coverage import Coverage
from tools.benchmark.runners import _build_coverage_result

from pyct import run_concolic
from tests.acceptance.fixtures.classes.docstringed_point import DocstringedPoint


def _class_header_line(cls: type) -> int:
    """Return the source line of the ``class`` statement."""
    return inspect.getsourcelines(cls)[1]


def _line_containing(cls: type, needle: str) -> int:
    """Return the absolute line number of the first line containing ``needle``."""
    src, start = inspect.getsourcelines(cls)
    for offset, line in enumerate(src):
        if needle in line:
            return start + offset
    raise AssertionError(f"{needle!r} not found in {cls.__name__} source")


def _all_statements_in_class(cls: type) -> set[int]:
    """Return coverage.py's executable-statement set restricted to ``cls``."""
    target_file = inspect.getfile(cls)
    src, start = inspect.getsourcelines(cls)
    func_range = set(range(start, start + len(src)))
    cov = Coverage(data_file=None, include=[target_file])
    return set(cov.analysis(target_file)[1]) & func_range


def test_engine_does_not_inject_class_header_into_executed_lines():
    """
    Given a class target with a docstring and a trivial __init__
    When run_concolic explores it
    Then executed_lines contains the body assignment lines
      And it does NOT contain the class header line — that line is only
          ever "covered" via the engine's internal pre_covered set and
          must not leak into the reported result.
    """
    class_line = _class_header_line(DocstringedPoint)
    assign_line = _line_containing(DocstringedPoint, "self.x = x")

    result = run_concolic(
        target=DocstringedPoint,
        initial_args={"x": 0, "y": 0, "z": 0, "m": 0},
    )

    assert result.success
    assert assign_line in result.executed_lines, (
        f"body line {assign_line} missing from {sorted(result.executed_lines)}"
    )
    assert class_line not in result.executed_lines, (
        f"class header line {class_line} leaked into executed_lines "
        f"{sorted(result.executed_lines)} — poisons _build_coverage_result backfill"
    )


def test_class_target_coverage_parity_llm_only_vs_engine():
    """
    Given the same class target executed both via raw coverage.py
         (llm_only path) and via the engine (concolic_llm path)
    When both results are passed through _build_coverage_result
    Then they report the same covered line count — the engine must not
         be penalized by its internal pre_covered accounting.
    """
    target = DocstringedPoint
    initial_args = {"x": 0, "y": 0, "z": 0, "m": 0}

    all_stmts = _all_statements_in_class(target)
    target_file = inspect.getfile(target)

    # Raw coverage.py path (what llm_only measures)
    cov = Coverage(data_file=None, include=[target_file])
    cov.start()
    target(**initial_args)
    cov.stop()
    raw_hits = set(cov.get_data().lines(target_file) or [])
    llm_only_result = _build_coverage_result(all_stmts, raw_hits)

    # Engine path (what concolic_llm measures)
    engine_result = run_concolic(target=target, initial_args=initial_args)
    assert engine_result.success
    concolic_result = _build_coverage_result(all_stmts, set(engine_result.executed_lines))

    assert concolic_result.executed_lines == llm_only_result.executed_lines, (
        f"coverage mismatch: concolic={concolic_result.executed_lines} "
        f"({sorted(concolic_result.executed_line_numbers)}) "
        f"vs llm_only={llm_only_result.executed_lines} "
        f"({sorted(llm_only_result.executed_line_numbers)})"
    )
