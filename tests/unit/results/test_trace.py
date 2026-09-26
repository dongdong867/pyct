import pytest

from pyct.core.branch import Branch, Expression, Site
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import (
    Aim,
    DowngradeCount,
    InputRecord,
    Miss,
    MissWhy,
    RunResult,
    Source,
    Stop,
    StopKind,
)
from pyct.results.trace import render_miss, render_stop, render_trace
from tests.unit.environment import ENVIRONMENT

FORK = Branch(expression=["<", "x", 10], taken=True, site=Site(file="m.py", line=5, col=7))
COVERAGE = Coverage(covered={"m.py": frozenset({6, 5})}, lines={"m.py": frozenset(range(1, 8))})


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


# a condition as the expression stores it, and the infix the fork line prints for it
INFIX: dict[str, tuple[Expression, str]] = {
    "method": (["startswith", "s", "'ab'"], "s.startswith('ab')"),
    "method-inside-a-compare": (["<", ["find", "s", "'x'"], "n"], "s.find('x') < n"),
    "method-on-a-condition": (["find", ["+", "s", "t"], "'x'"], "(s + t).find('x')"),
    "keyword": (["in", "'a'", "s"], "'a' in s"),
    "builtin": (["abs", "x"], "abs x"),
    "unary-minus": (["-", "x"], "- x"),
}


@pytest.mark.parametrize(("expression", "written"), INFIX.values(), ids=list(INFIX))
def test_render_trace_writes_the_condition_as_python_does(
    expression: Expression, written: str
) -> None:
    fork = Branch(expression=expression, taken=True, site=Site(file="m.py", line=5, col=7))
    record = InputRecord(args={"s": "a"}, forks=(fork,), covered_lines=frozenset({5}))

    lines = render_trace(record, COVERAGE).splitlines()

    # a method call binds tighter than any operator, so it needs no parentheses of its own
    assert lines[1] == f"fork m.py:5:7  {written}  taken"


def test_render_trace_reads_the_counts_from_the_coverage_maps() -> None:
    # the record holds the target's own lines; the maps are what the trace counts
    coverage = Coverage(
        covered={"m.py": frozenset({1, 2, 3})}, lines={"m.py": frozenset(range(1, 10))}
    )
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


def test_render_trace_joins_the_downgrades_in_order_and_counts_a_run() -> None:
    record = InputRecord(
        args={"x": 1},
        forks=(),
        covered_lines=frozenset(),
        downgrades=(
            DowngradeCount(name="__radd__", count=3),
            DowngradeCount(name="__abs__", count=1),
        ),
    )

    lines = render_trace(record, COVERAGE).splitlines()

    # one call is the bare name; more than one carries the count after it
    assert lines[-1] == "downgrades __radd__ ×3, __abs__"


def test_render_trace_opens_a_seed_with_the_word_seed() -> None:
    record = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset())

    lines = render_trace(record, COVERAGE).splitlines()

    assert lines[0] == 'seed {"x": 1}'


def test_render_trace_opens_a_solved_input_with_the_word_solver_and_its_aim() -> None:
    record = InputRecord(
        args={"x": 12},
        forks=(FORK,),
        covered_lines=frozenset({5}),
        source=Source.SOLVER,
        aim=Aim(site=Site(file="m.py", line=5, col=7), position=0),
    )

    lines = render_trace(record, COVERAGE).splitlines()

    assert lines[:4] == [
        'solver {"x": 12}',
        "aim m.py:5:7 at position 0",
        "reached",
        "fork m.py:5:7  x < 10  taken",
    ]


def test_render_trace_says_where_a_solved_input_left_the_plan() -> None:
    record = InputRecord(
        args={"x": 12},
        forks=(FORK,),
        covered_lines=frozenset({5}),
        source=Source.SOLVER,
        aim=Aim(site=Site(file="m.py", line=9, col=3), position=1),
        mismatch_at=1,
    )

    lines = render_trace(record, COVERAGE).splitlines()

    # the record forked once, so the plan's position 1 is past everything it did
    assert lines[:3] == [
        'solver {"x": 12}',
        "aim m.py:9:3 at position 1",
        "left the plan at position 1, no fork there",
    ]


def test_render_trace_names_the_fork_a_solved_input_hit_instead() -> None:
    elsewhere = Branch(expression=["<", "y", 3], taken=True, site=Site(file="m.py", line=12, col=4))
    record = InputRecord(
        args={"x": 12},
        forks=(FORK, elsewhere),
        covered_lines=frozenset({5}),
        source=Source.SOLVER,
        aim=Aim(site=Site(file="m.py", line=9, col=3), position=1),
        mismatch_at=1,
    )

    lines = render_trace(record, COVERAGE).splitlines()

    assert lines[2] == "left the plan at position 1, hit m.py:12:4"


def test_render_miss_names_the_fork_and_what_the_solver_said() -> None:
    miss = Miss(site=Site(file="m.py", line=5, col=7), why=MissWhy.UNSAT)

    text = render_miss(miss)

    # one fact on one line, ended the way every other line of the trace ends
    assert text == "missed m.py:5:7 unsat\n"


def stopped_with(stop: Stop, *misses: Miss) -> RunResult:
    """A run result whose only facts that matter here are how it ended and what it missed."""
    record = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset())
    return RunResult(
        entry="m::f",
        records=(record,),
        coverage=COVERAGE,
        stopped=stop,
        environment=ENVIRONMENT,
        misses=misses,
    )


def test_render_stop_sums_the_run_and_ends_on_why_it_stopped() -> None:
    lines = render_stop(stopped_with(Stop(kind=StopKind.NO_FORK))).splitlines()

    # the coverage is worded the way each input's own trace words it, over the run's counts
    assert lines == [
        "covered 2 of 7 lines in m.py",
        "solver: 0 sat, 0 unsat, 0 unknown, 0 timeout",
        "uncovered 1, 2, 3, 4, 7 in m.py",
        "stopped: no fork to flip",
    ]


def test_render_stop_reads_the_plateau_into_why_the_run_stopped() -> None:
    lines = render_stop(stopped_with(Stop(kind=StopKind.NO_GAIN, plateau=3))).splitlines()

    assert lines[-1] == "stopped: no gain in 3 inputs"


def test_render_stop_counts_what_the_solver_answered() -> None:
    solved = InputRecord(
        args={"x": 12}, forks=(), covered_lines=frozenset({6}), source=Source.SOLVER
    )
    result = RunResult(
        entry="m::f",
        records=(InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset({5})), solved),
        coverage=COVERAGE,
        stopped=Stop(kind=StopKind.NO_FORK),
        environment=ENVIRONMENT,
        misses=(Miss(site=Site(file="m.py", line=9, col=3), why=MissWhy.TIMEOUT),),
    )

    lines = render_stop(result).splitlines()

    # the miss it timed out on is counted here, though its own line printed during the run
    assert lines[1] == "solver: 1 sat, 0 unsat, 0 unknown, 1 timeout"


def test_render_stop_leaves_the_missed_lines_to_the_run() -> None:
    miss = Miss(site=Site(file="m.py", line=5, col=7), why=MissWhy.UNSAT)

    lines = render_stop(stopped_with(Stop(kind=StopKind.NO_FORK), miss)).splitlines()

    # each miss printed as its answer came in; the summary starts at its first covered line
    assert lines == [
        "covered 2 of 7 lines in m.py",
        "solver: 0 sat, 1 unsat, 0 unknown, 0 timeout",
        "uncovered 1, 2, 3, 4, 7 in m.py",
        "stopped: no fork to flip",
    ]


def test_render_stop_leaves_out_a_file_with_nothing_uncovered() -> None:
    covered = Coverage(covered={"m.py": frozenset({1, 2})}, lines={"m.py": frozenset({1, 2})})
    result = RunResult(
        entry="m::f",
        records=(InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset({1, 2})),),
        coverage=covered,
        stopped=Stop(kind=StopKind.NO_FORK),
        environment=ENVIRONMENT,
    )

    lines = render_stop(result).splitlines()

    assert not [line for line in lines if line.startswith("uncovered ")], lines


def test_render_stop_indents_what_the_solver_said_under_the_stop_line() -> None:
    stop = Stop(kind=StopKind.SOLVER_FAILED, detail="cvc5: boom\nsegmentation fault")

    lines = render_stop(stopped_with(stop)).splitlines()

    assert lines[-3:] == ["stopped: solver failed", "    cvc5: boom", "    segmentation fault"]
