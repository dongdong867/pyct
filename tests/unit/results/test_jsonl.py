import json

from pyct.core.branch import Branch, Site
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure, FailureKind
from pyct.results.jsonl import render, render_summary
from pyct.results.record import (
    Aim,
    DowngradeCount,
    Environment,
    InputRecord,
    Miss,
    MissWhy,
    RunResult,
    Source,
    Stop,
    StopKind,
)
from tests.unit.environment import ENVIRONMENT

FORK = Branch(expression=["<", "x", 10], taken=True, site=Site(file="m.py", line=5, col=7))
COVERAGE = Coverage(covered={"m.py": frozenset({6, 5})}, lines={"m.py": frozenset(range(1, 8))})
SEED = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset({5}))
SOLVED = InputRecord(args={"x": 12}, forks=(), covered_lines=frozenset({6}), source=Source.SOLVER)
MISS = Miss(site=Site(file="m.py", line=5, col=7), why=MissWhy.UNSAT)


def test_render_is_one_json_line_with_sorted_lines() -> None:
    record = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset({6, 5}))

    line = render(record, COVERAGE)

    assert "\n" not in line
    assert json.loads(line) == {
        "args": {"x": 1},
        "forks": [],
        "covered": {"m.py": [5, 6]},
        "total": {"m.py": 7},
        "failure": None,
        "downgrades": [],
        "source": "seed",
        "aim": None,
        "mismatch_at": None,
    }


def test_render_writes_each_fork_with_its_site_and_expression() -> None:
    record = InputRecord(args={"x": 1}, forks=(FORK,), covered_lines=frozenset({5}))

    payload = json.loads(render(record, COVERAGE))

    assert payload["forks"] == [
        {"file": "m.py", "line": 5, "col": 7, "taken": True, "expression": ["<", "x", 10]}
    ]


def test_render_puts_the_forks_between_the_args_and_the_coverage() -> None:
    record = InputRecord(args={"x": 1}, forks=(FORK,), covered_lines=frozenset({5}))

    payload = json.loads(render(record, COVERAGE))

    assert list(payload) == [
        "args",
        "forks",
        "covered",
        "total",
        "failure",
        "downgrades",
        "source",
        "aim",
        "mismatch_at",
    ]


def test_render_keeps_the_forks_in_execution_order() -> None:
    second = Branch(expression="y", taken=False, site=Site(file="m.py", line=9, col=3))
    record = InputRecord(args={"x": 1}, forks=(FORK, second), covered_lines=frozenset({5}))

    payload = json.loads(render(record, COVERAGE))

    assert [fork["line"] for fork in payload["forks"]] == [5, 9]


def test_render_writes_the_failure_as_its_kind_and_detail() -> None:
    failure = Failure(kind=FailureKind.TARGET_RAISED, detail="ValueError: too small")
    record = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset(), failure=failure)

    payload = json.loads(render(record, COVERAGE))

    assert payload["failure"] == {"kind": "target_raised", "detail": "ValueError: too small"}


def test_render_lists_the_downgrades_in_order_with_their_counts() -> None:
    record = InputRecord(
        args={"x": 1},
        forks=(),
        covered_lines=frozenset(),
        downgrades=(
            DowngradeCount(name="__abs__", count=3),
            DowngradeCount(name="__add__", count=1),
        ),
    )

    payload = json.loads(render(record, COVERAGE))

    assert payload["downgrades"] == [
        {"name": "__abs__", "count": 3},
        {"name": "__add__", "count": 1},
    ]


def test_render_keeps_the_traceback_off_the_line() -> None:
    # the traceback is for the person reading stderr; the line stays one kind and one detail
    failure = Failure(
        kind=FailureKind.PYCT_BUG, detail="RuntimeError: boom", traceback="Traceback...\nboom\n"
    )
    record = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset(), failure=failure)

    payload = json.loads(render(record, COVERAGE))

    assert payload["failure"] == {"kind": "pyct_bug", "detail": "RuntimeError: boom"}


def test_render_writes_a_seed_as_coming_from_the_seed_with_nothing_aimed_at() -> None:
    record = InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset())

    payload = json.loads(render(record, COVERAGE))

    assert payload["source"] == "seed"
    assert payload["aim"] is None
    assert payload["mismatch_at"] is None


def test_render_writes_the_aim_as_its_site_and_its_position() -> None:
    record = InputRecord(
        args={"x": 12},
        forks=(FORK,),
        covered_lines=frozenset({5}),
        source=Source.SOLVER,
        aim=Aim(site=Site(file="m.py", line=5, col=7), position=0),
    )

    payload = json.loads(render(record, COVERAGE))

    assert payload["source"] == "solver"
    assert payload["aim"] == {"file": "m.py", "line": 5, "col": 7, "position": 0}


def test_render_writes_the_position_where_the_input_left_the_plan() -> None:
    record = InputRecord(
        args={"x": 12},
        forks=(FORK,),
        covered_lines=frozenset({5}),
        source=Source.SOLVER,
        aim=Aim(site=Site(file="m.py", line=5, col=7), position=1),
        mismatch_at=1,
    )

    payload = json.loads(render(record, COVERAGE))

    assert payload["mismatch_at"] == 1


def summarized(
    *records: InputRecord,
    stopped: StopKind | Stop = StopKind.NO_FORK,
    misses: tuple[Miss, ...] = (),
) -> dict[str, object]:
    """The summary of a run whose only facts that matter here are its records and misses.

    A bare kind is the usual case; a whole ``Stop`` is for the kinds that
    carry more than their name.
    """
    result = RunResult(
        entry="m::f",
        records=records,
        coverage=Coverage(
            covered={"m.py": frozenset({6, 5})}, lines={"m.py": frozenset(range(1, 8))}
        ),
        stopped=stopped if isinstance(stopped, Stop) else Stop(kind=stopped),
        environment=ENVIRONMENT,
        misses=misses,
    )
    return json.loads(render_summary(result))


def test_render_summary_is_one_json_line_with_its_keys_in_order() -> None:
    line = render_summary(
        RunResult(
            entry="m::f",
            records=(SEED,),
            coverage=COVERAGE,
            stopped=Stop(kind=StopKind.NO_FORK),
            environment=ENVIRONMENT,
        )
    )

    assert "\n" not in line
    assert list(json.loads(line)) == [
        "stopped",
        "inputs",
        "solver",
        "misses",
        "covered",
        "total",
        "uncovered",
        "environment",
    ]


def test_render_summary_says_why_the_run_stopped_and_how_many_inputs_ran() -> None:
    payload = summarized(SEED, SOLVED, stopped=StopKind.BUDGET)

    assert payload["stopped"] == "budget spent"
    assert payload["inputs"] == 2


def test_render_summary_reads_the_plateau_into_why_the_run_stopped() -> None:
    payload = summarized(SEED, SOLVED, stopped=Stop(kind=StopKind.NO_GAIN, plateau=3))

    assert payload["stopped"] == "no gain in 3 inputs"


def test_render_summary_counts_the_solver_answers_by_kind() -> None:
    payload = summarized(SEED, SOLVED, misses=(MISS,))

    assert payload["solver"] == {"sat": 1, "unsat": 1, "unknown": 0, "timeout": 0}


def test_render_summary_writes_each_miss_as_its_site_and_the_answer() -> None:
    timed_out = Miss(site=Site(file="m.py", line=9, col=3), why=MissWhy.TIMEOUT)

    payload = summarized(SEED, misses=(MISS, timed_out))

    assert payload["misses"] == [
        {"file": "m.py", "line": 5, "col": 7, "why": "unsat"},
        {"file": "m.py", "line": 9, "col": 3, "why": "timeout"},
    ]


def test_render_summary_writes_the_coverage_the_way_an_input_line_does() -> None:
    payload = summarized(SEED)

    assert payload["covered"] == {"m.py": [5, 6]}
    assert payload["total"] == {"m.py": 7}


def test_render_summary_lists_the_lines_no_input_ran() -> None:
    payload = summarized(SEED)

    # the lines the file has, less the ones the run covered, ascending
    assert payload["uncovered"] == {"m.py": [1, 2, 3, 4, 7]}


def test_render_summary_leaves_a_fully_covered_file_an_empty_list() -> None:
    result = RunResult(
        entry="m::f",
        records=(SEED,),
        coverage=Coverage(covered={"m.py": frozenset({1, 2})}, lines={"m.py": frozenset({1, 2})}),
        stopped=Stop(kind=StopKind.NO_FORK),
        environment=ENVIRONMENT,
    )

    # uncovered is keyed like total, so a file it counts is on the line either way
    assert json.loads(render_summary(result))["uncovered"] == {"m.py": []}


def test_render_summary_names_the_python_the_cvc5_the_platform_and_the_isolation() -> None:
    payload = summarized(SEED)

    assert payload["environment"] == {
        "python": "3.12.0",
        "cvc5": "1.2.1",
        "platform": "Test-1.0-arm64",
        "isolated": True,
    }


def test_render_summary_names_no_cvc5_when_the_probe_failed() -> None:
    result = RunResult(
        entry="m::f",
        records=(SEED,),
        coverage=COVERAGE,
        stopped=Stop(kind=StopKind.NO_FORK),
        environment=Environment(
            python="3.12.0", cvc5=None, platform="Test-1.0-arm64", isolated=True
        ),
    )

    assert json.loads(render_summary(result))["environment"]["cvc5"] is None
