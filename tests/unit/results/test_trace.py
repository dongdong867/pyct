import pytest

from pyct.core.branch import Branch, Site
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import InputRecord
from pyct.results.trace import render_trace

FORK = Branch(expression=["<", "x", 10], taken=True, site=Site(file="m.py", line=5, col=7))
COVERAGE = Coverage(covered={"m.py": frozenset({6, 5})}, total={"m.py": 7})


def test_render_trace_puts_one_fact_on_each_line_in_order() -> None:
    record = InputRecord(args={"x": 1}, forks=(FORK,), covered_lines=frozenset({6, 5}))

    text = render_trace(record, COVERAGE)

    assert text.endswith("\n")
    assert text.splitlines() == [
        'seed {"x": 1}',
        "fork m.py:5:7  x < 10  taken",
        "covered 2 of 7 lines in m.py",
        "ended returned",
        "downgrades none",
    ]


def test_render_trace_writes_each_fork_in_order_with_the_side_taken() -> None:
    second = Branch(expression=["<", "y", 3], taken=False, site=Site(file="m.py", line=9, col=3))
    record = InputRecord(args={"x": 1}, forks=(FORK, second), covered_lines=frozenset({5}))

    lines = render_trace(record, COVERAGE).splitlines()

    assert lines[1:3] == ["fork m.py:5:7  x < 10  taken", "fork m.py:9:3  y < 3  not taken"]


def test_render_trace_wraps_a_nested_condition_in_parentheses() -> None:
    fork = Branch(
        expression=["<", ["+", "x", 1], ["-", "y", 2]],
        taken=True,
        site=Site(file="m.py", line=5, col=7),
    )
    record = InputRecord(args={"x": 1}, forks=(fork,), covered_lines=frozenset({5}))

    lines = render_trace(record, COVERAGE).splitlines()

    assert lines[1] == "fork m.py:5:7  (x + 1) < (y - 2)  taken"


def test_render_trace_reads_the_counts_from_the_coverage_maps() -> None:
    # the record holds the target's own lines; the maps are what the trace counts
    coverage = Coverage(covered={"m.py": frozenset({1, 2, 3})}, total={"m.py": 9})
    record = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset({5}))

    lines = render_trace(record, coverage).splitlines()

    assert lines[1] == "covered 3 of 9 lines in m.py"


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (FailureKind.TIMEOUT, "ended timeout: gave up"),
        (FailureKind.TARGET_RAISED, "ended target raised: gave up"),
        (FailureKind.SYSTEM_EXIT, "ended system exit: gave up"),
        (FailureKind.PYCT_BUG, "ended pyct bug: gave up"),
    ],
)
def test_render_trace_names_the_kind_in_words(kind: FailureKind, expected: str) -> None:
    failure = Failure(kind=kind, detail="gave up")
    record = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset(), failure=failure)

    lines = render_trace(record, COVERAGE).splitlines()

    assert lines[2] == expected


def test_render_trace_indents_the_traceback_under_the_ended_line() -> None:
    failure = Failure(
        kind=FailureKind.PYCT_BUG,
        detail="RuntimeError: boom",
        traceback="Traceback (most recent call last):\nRuntimeError: boom\n",
    )
    record = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset(), failure=failure)

    lines = render_trace(record, COVERAGE).splitlines()

    assert lines[2:5] == [
        "ended pyct bug: RuntimeError: boom",
        "    Traceback (most recent call last):",
        "    RuntimeError: boom",
    ]


def test_render_trace_leaves_out_the_traceback_a_failure_does_not_carry() -> None:
    failure = Failure(kind=FailureKind.TARGET_RAISED, detail="ValueError: too small")
    record = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset(), failure=failure)

    lines = render_trace(record, COVERAGE).splitlines()

    assert lines[3] == "downgrades none"


def test_render_trace_joins_the_downgrades_in_order() -> None:
    record = InputRecord(
        args={"x": 1}, forks=(), covered_lines=frozenset(), downgrades=("__abs__", "__add__")
    )

    lines = render_trace(record, COVERAGE).splitlines()

    assert lines[-1] == "downgrades __abs__, __add__"
