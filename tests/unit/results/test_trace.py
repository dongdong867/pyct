import math
import re

import pytest

from pyct.core.branch import Branch, Expression, Site
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure, FailureKind
from pyct.results.printed import LIMIT
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


def test_render_trace_wraps_an_operand_only_where_python_needs_it() -> None:
    fork = Branch(
        expression=["<", ["+", "x", 1], ["-", "y", 2]],
        taken=True,
        site=Site(file="m.py", line=5, col=7),
    )
    record = InputRecord(args={"x": 1}, forks=(fork,), covered_lines=frozenset({5}))

    lines = render_trace(record, COVERAGE).splitlines()

    # `+` and `-` bind tighter than `<`, so the line reads as the target wrote it
    assert lines[1] == "fork m.py:5:7  x + 1 < y - 2  taken"


# a condition as the expression stores it, and the infix the fork line prints for it
INFIX: dict[str, tuple[Expression, str]] = {
    "method": (["startswith", "s", "'ab'"], "s.startswith('ab')"),
    "method-inside-a-compare": (["<", ["find", "s", "'x'"], "n"], "s.find('x') < n"),
    "method-on-a-condition": (["find", ["+", "s", "t"], "'x'"], "(s + t).find('x')"),
    "keyword": (["in", "'a'", "s"], "'a' in s"),
    "builtin": (["abs", "x"], "abs(x)"),
    "unary-minus": (["-", "x"], "-x"),
    "key": (["[]", "config", "'port'"], "config['port']"),
    # a call binds tighter than any operator, so it never gets parentheses of its own
    "builtin-under-a-unary-minus": (["<", ["-", ["abs", "x"]], -3], "-abs(x) < -3"),
    "builtin-as-the-base-of-a-power": ([">", ["**", ["abs", "x"], 2], 9], "abs(x) ** 2 > 9"),
    "builtin-of-a-sum": ([">", ["abs", ["-", "x", 1]], 3], "abs(x - 1) > 3"),
    "builtin-of-a-builtin": (
        [">", ["abs", ["-", ["abs", "x"], 5]], 1],
        "abs(abs(x) - 5) > 1",
    ),
    "length-of-a-sum": (["len", ["+", "s", "t"]], "len(s + t)"),
    # a builtin's name the table does not hold is a method, as `format` and `hex` are on a
    # str and a float
    "builtin-name-on-a-receiver": (["hex", "x"], "x.hex()"),
    "builtin-name-with-an-argument": (["format", "s", "'x'"], "s.format('x')"),
    "unary-minus-of-a-unary-minus": ([">", ["-", ["-", "x"]], 1], "--x > 1"),
    "unary-minus-of-a-negative-number": (["-", -3], "--3"),
    "unary-invert": (["~", "x"], "~x"),
    "unary-plus-of-a-compare": (["+", [">", "x", 0]], "+(x > 0)"),
    # a head that is neither an operator, a function nor a name keeps `op a`, in parentheses
    # as any operand
    "keyword-on-one-operand": (["==", ["not", "x"], True], "(not x) == True"),
    "key-of-a-key": (
        ["<", ["[]", ["[]", "config", "'server'"], "'port'"], 1],
        "config['server']['port'] < 1",
    ),
    "key-in-double-quotes": (["[]", "d", '"it\'s"'], 'd["it\'s"]'),
    "item-index": (["==", ["[]", "items", 0], ["[]", "items", 1]], "items[0] == items[1]"),
    "method-on-an-item": (["find", ["[]", "items", 0], "'x'"], "items[0].find('x')"),
    "index-of-a-condition": (["[]", ["+", "s", "t"], 0], "(s + t)[0]"),
    "index": (["[]", "s", 0], "s[0]"),
    "negative-index": (["[]", "s", -1], "s[-1]"),
    "slice": (["[:]", "s", 1, 3], "s[1:3]"),
    "slice-missing-stop": (["[:]", "s", 2, None], "s[2:]"),
    "slice-missing-start": (["[:]", "s", None, -1], "s[:-1]"),
    "length": ([">", ["len", "s"], 3], "len(s) > 3"),
    "in-a-range": (["in", "port", ["range", 1, 65536]], "port in range(1, 65536)"),
    "not-in-a-stepped-range": (["not in", 5, ["range", 0, "n", -2]], "5 not in range(0, n, -2)"),
    "tracked-index": (["[]", "s", "n"], "s[n]"),
    "long-enough-for-a-tracked-index": ([">", ["len", "s"], "n"], "len(s) > n"),
    "reversed": (["==", ["[:]", "s", None, None, -1], "'abc'"], "s[::-1] == 'abc'"),
    "backward-between-bounds": (["[:]", "s", "n", 0, -1], "s[n:0:-1]"),
    "slice-at-a-search": (["[:]", "s", None, ["find", "s", "'='"]], "s[:s.find('=')]"),
    "search-from-a-position": (["find", "s", "'y'", None, "n"], "s.find('y', None, n)"),
    "tuple-of-prefixes": (
        ["startswith", "s", ["()", "'GET'", "'POST'"]],
        "s.startswith(('GET', 'POST'))",
    ),
    "tuple-of-one": (["endswith", "s", ["()", "'a'"], "n"], "s.endswith(('a',), n)"),
    "replace-once": (["replace", "s", "'a'", "'b'", 1], "s.replace('a', 'b', 1)"),
    "code": (["==", ["ord", "c"], 65], "ord(c) == 65"),
    "character": (["==", ["chr", "n"], "'z'"], "chr(n) == 'z'"),
    "code-of-a-piece": (["ord", ["[]", "s", 0]], "ord(s[0])"),
    "piece-inside-a-compare": (["==", ["[]", "s", 0], "'a'"], "s[0] == 'a'"),
    "method-on-a-piece": (
        ["removeprefix", ["[:]", "s", 1, None], "'x'"],
        "s[1:].removeprefix('x')",
    ),
    "replace": (["replace", "s", "'a'", "'b'"], "s.replace('a', 'b')"),
    "check-with-no-argument": (["isdigit", "s"], "s.isdigit()"),
    "method-on-a-method": (["==", ["strip", ["upper", "s"]], "'A'"], "s.upper().strip() == 'A'"),
    "piece-of-a-split": (
        ["==", ["[]", ["split", "s", None, 1], 0], "'a'"],
        "s.split(None, 1)[0] == 'a'",
    ),
    "cut-part": (["==", ["...", 5000], "'abc'"], "...(5000 nodes) == 'abc'"),
    "piece-of-a-cut-part": (["[]", ["...", 12], 0], "...(12 nodes)[0]"),
    "uncounted-cut-part": (["==", ["...", None], "'abc'"], "...(? nodes) == 'abc'"),
    "bool-literal": ([">", ["+", "x", True], 5], "x + True > 5"),
    "looser-operand": (["*", ["+", "x", 1], 2], "(x + 1) * 2"),
    "left-operand-of-the-same-binding": (["-", ["-", "x", 1], 2], "x - 1 - 2"),
    "right-operand-of-the-same-binding": (["-", "x", ["-", 1, 2]], "x - (1 - 2)"),
    "chain-of-sums": ([">", ["+", ["+", "x", "y"], "z"], 10], "x + y + z > 10"),
    "compare-of-compares": (["==", [">", "x", 0], [">", "y", 0]], "(x > 0) == (y > 0)"),
    "count-of-compares": (
        ["==", ["+", [">", "x", 0], [">", "y", 0]], 2],
        "(x > 0) + (y > 0) == 2",
    ),
    "and-of-compares": (["&", [">", "x", 0], [">", "y", 0]], "(x > 0) & (y > 0)"),
    "and-inside-a-compare": (["==", ["&", "a", "b"], True], "a & b == True"),
    "unary-minus-inside-a-sum": (["+", ["-", "x"], 1], "-x + 1"),
    "unary-minus-inside-a-compare": (["<", ["-", "x"], -3], "-x < -3"),
    "power-under-a-unary-minus": (["-", ["**", "x", 2]], "-x ** 2"),
    "unary-minus-under-a-power": (["**", ["-", "x"], 2], "(-x) ** 2"),
    "negative-base-of-a-power": (["**", -2, "x"], "(-2) ** x"),
    "unary-minus-exponent": (["**", "x", ["-", "y"]], "x ** -y"),
    "power-of-a-power": (["**", ["**", "x", "y"], 2], "(x ** y) ** 2"),
    "power-exponent": (["**", "x", ["**", "y", 2]], "x ** y ** 2"),
    "sum-under-a-unary-minus": (["-", ["+", "x", 1]], "-(x + 1)"),
    "compare-in-a-sum": (["+", [">", "x", 0], 1], "(x > 0) + 1"),
    "sum-of-a-count": (
        ["==", ["+", ["+", 0, [">", "x", 5]], [">", "y", 5]], 0],
        "0 + (x > 5) + (y > 5) == 0",
    ),
    "method-on-a-negative-number": (["find", -1, "'x'"], "(-1).find('x')"),
    "operator-the-table-does-not-rank": (["@", ["+", "x", 1], "y"], "(x + 1) @ y"),
    "list-display": (["[]", ["+", "items", ["[,]", "x", 7]], 2], "(items + [x, 7])[2]"),
    "empty-display": (["==", ["len", ["[,]"]], 0], "len([]) == 0"),
    "floats-python-reads-back": (
        ["[,]", 1.5, float("nan"), float("inf"), float("-inf")],
        "[1.5, float('nan'), float('inf'), -float('inf')]",
    ),
    # a float literal as repr writes it
    "float-exponent": (["<", "x", 1e-05], "x < 1e-05"),
    "float-whole": (["!=", "x", 2.0], "x != 2.0"),
    # an infinity as the call that makes it, which Python reads back
    "float-infinity": ([">", "x", math.inf], "x > float('inf')"),
    "float-minus-infinity": ([">", "x", -math.inf], "x > -float('inf')"),
    "float-nan": (["!=", "x", math.nan], "x != float('nan')"),
    # a minus infinity binds as a unary minus, so it needs parentheses as the base of `**`
    "minus-infinity-as-a-base": (["**", -math.inf, "x"], "(-float('inf')) ** x"),
    "method-with-no-argument": (["is_integer", "x"], "x.is_integer()"),
    "method-with-no-argument-on-a-condition": (
        ["is_integer", ["/", "x", "y"]],
        "(x / y).is_integer()",
    ),
    # a rounding and the finite check as the target calls them, from math or the builtins
    "floor": (["==", ["floor", "x"], 3], "math.floor(x) == 3"),
    "ceil-of-a-sum": (["<", ["ceil", ["+", "x", 0.5]], "n"], "math.ceil(x + 0.5) < n"),
    "trunc": (["==", ["trunc", "x"], -2], "math.trunc(x) == -2"),
    "round": (["==", ["round", "x"], 2], "round(x) == 2"),
    "finite": (["isfinite", "x"], "math.isfinite(x)"),
}


@pytest.mark.parametrize(("expression", "written"), INFIX.values(), ids=list(INFIX))
def test_render_trace_writes_the_condition_as_python_does(
    expression: Expression, written: str
) -> None:
    fork = Branch(expression=expression, taken=True, site=Site(file="m.py", line=5, col=7))
    record = InputRecord(args={"s": "a"}, forks=(fork,), covered_lines=frozenset({5}))

    lines = render_trace(record, COVERAGE).splitlines()

    # a method call, an index, a slice and len bind tighter than any operator, so none needs
    # parentheses of its own
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


def test_render_trace_writes_an_expression_past_the_cap_cut() -> None:
    term: Expression = "s"
    for _ in range(40):
        term = ["+", ["[:]", term, None, 1], ["[:]", term, 2, None]]
    fork = Branch(expression=["==", term, "'abc'"], taken=False, site=Site("m.py", 5, 7))
    record = InputRecord(args={"s": "abc"}, forks=(fork,), covered_lines=frozenset({5}))

    lines = render_trace(record, COVERAGE).splitlines()

    # the fork line holds what the stdout line holds, each cut part as the distinct nodes it holds
    assert lines[1].startswith("fork m.py:5:7  (")
    assert lines[1].endswith(" == 'abc'  not taken")
    assert " nodes)" in lines[1]
    assert len(lines[1]) < 20_000


def test_render_trace_writes_a_condition_nested_past_the_recursion_limit() -> None:
    term: Expression = "x"
    for _ in range(LIMIT - 1):
        term = ["abs", term]
    # LIMIT nodes, so the line prints it whole, nested deeper than Python's recursion limit
    fork = Branch(expression=term, taken=True, site=Site("m.py", 5, 7))
    record = InputRecord(args={"x": 1}, forks=(fork,), covered_lines=frozenset({5}))

    lines = render_trace(record, COVERAGE).splitlines()

    nested = LIMIT - 1
    assert lines[1] == f"fork m.py:5:7  {'abs(' * nested}x{')' * nested}  taken"


def test_render_trace_writes_a_string_built_over_five_thousand_passes() -> None:
    term: Expression = "s"
    for _ in range(5000):
        term = ["+", term, "' '"]
    fork = Branch(expression=["startswith", term, "'ok'"], taken=False, site=Site("m.py", 5, 7))
    record = InputRecord(args={"s": "a"}, forks=(fork,), covered_lines=frozenset({5}))

    lines = render_trace(record, COVERAGE).splitlines()

    # the top of the string is kept over the cut part, each pass one more sum, as Python reads a
    # chain of them from the left
    assert re.fullmatch(
        r"fork m\.py:5:7  \(\.\.\.\(\d+ nodes\)( \+ ' ')+\)\.startswith\('ok'\)  not taken",
        lines[1],
    )
