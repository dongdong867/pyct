"""Acceptance tests for keep-a-target-s-own-failures-out-of-pyct-bugs.

An input that never ends, and a target's own recursion past Python's limit, are the target's
behavior: each input's line says so as its own ending, and the run exits 0.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.execution import tally
from pyct.results.failure import FailureKind
from pyct.results.record import Stop, StopKind
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.target import load_target
from tests.acceptance.harness import REPO_ROOT, first_line, forks_of, input_lines, run_pyct
from tests.acceptance.timed import measured

ENDLESS = "targets.isolate.endless::spin"
DEEP = "targets.isolate.deep::deep"

# the largest n plain Python's `deep(n)` returns for, called from a module's top level
_PLAIN_DEPTH = """
import sys
from targets.isolate.deep import deep
low, high = 0, sys.getrecursionlimit()
while low < high:
    middle = (low + high + 1) // 2
    try:
        deep(middle)
        low = middle
    except RecursionError:
        high = middle - 1
print(low)
"""

# what plain Python says when `deep` passes its recursion limit, called the same way
_PLAIN_RAISE = """
from targets.isolate.deep import deep
try:
    deep(100_000)
except RecursionError as error:
    print(f"{type(error).__name__}: {error}")
"""


def _plain(script: str) -> str:
    """What ``script`` prints, run by plain Python from the repository root."""
    finished = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return finished.stdout.strip()


# keep-a-target-s-own-failures-out-of-pyct-bugs-ends-an-endless-input-as-its-own
def test_an_endless_input_ends_as_its_own_and_the_run_stops_normally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tally, "MOST_FORKS", 1_000)
    target = load_target(ENDLESS)

    # forked, as the command line forks it: the test's own timeout thread would move it to a
    # fresh interpreter
    result = run(
        target, {"n": 0, "m": 0}, limits=Limits(budget=Budget(4)), isolation=Isolation.FORK
    )

    kinds = [None if record.failure is None else record.failure.kind for record in result.records]
    assert FailureKind.PYCT_BUG not in kinds, result.records
    endless = kinds.index(FailureKind.TOO_LONG)
    record = result.records[endless]
    assert record.args["n"] == 7
    assert len(record.forks) == 1_000
    assert record.failure is not None
    assert record.failure.detail == (
        "the input took more than 1000 forks, the most pyct keeps for one input"
    )
    # the input runs on past its bound until its deadline, which spends the run's budget
    assert result.stopped == Stop(StopKind.BUDGET)


# keep-a-target-s-own-failures-out-of-pyct-bugs-ends-an-endless-input-as-its-own
def test_an_input_past_its_bound_that_outlasts_the_deadline_still_ends_as_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tally, "MOST_FORKS", 1_000)
    target = load_target("targets.isolate.endless::outlast")

    # it catches the deadline's raise, so pyct kills its process and it writes no ending
    result = run(target, {"n": 1}, limits=Limits(budget=Budget(2)), isolation=Isolation.FORK)

    (seed,) = result.records
    assert seed.failure is not None
    assert seed.failure.kind is FailureKind.TOO_LONG, seed.failure
    assert len(seed.forks) == 1_000


@pytest.mark.serial
# keep-a-target-s-own-failures-out-of-pyct-bugs-bounds-one-input-s-record
def test_an_endless_seed_lists_the_bound_s_forks_and_exits_zero_within_the_margin(
    tmp_path: Path,
) -> None:
    budget = 4
    run_ = measured(tmp_path, [ENDLESS, "--args", '{"n": 7, "m": 0}', "--budget", str(budget)])

    assert run_.returncode == 0, run_.stderr[-2000:]
    seed = input_lines(run_.stdout)[0]
    assert seed["failure"] == {
        "kind": "too_long",
        "detail": "the input took more than 200000 forks, the most pyct keeps for one input",
    }
    # the forks up to the bound, in the order the call took them: `m > 3`, `n == 7`, then the
    # loop's test on every pass
    forks = [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(seed)]
    assert forks[:2] == [(2, [">", "m", 3], False), (4, ["==", "n", 7], True)]
    # past the line's 100,000 nodes a fork's expression prints cut, as its three nodes
    passes = {json.dumps([6, [">", "n", 0], True]), json.dumps([6, ["...", 3], True])}
    assert all(json.dumps(list(fork)) in passes for fork in forks[2:])
    assert len(forks) == 200_000
    # the README's isolation rule: a second past the deadline for 100,000 forks on a line, and
    # half a second for each further 100,000
    assert run_.wall < budget + 1.5, run_.wall


# keep-a-target-s-own-failures-out-of-pyct-bugs-keeps-the-target-s-recursion-error
def test_a_target_s_own_recursion_error_is_the_target_s() -> None:
    expected = _plain(_PLAIN_RAISE)

    result = run_pyct(DEEP, "--args", json.dumps({"n": 100_000}), "--budget", "3")

    assert result.returncode == 0, result.stderr[-2000:]
    assert first_line(result.stdout)["failure"] == {"kind": "target_raised", "detail": expected}
    assert "pyct_bug" not in result.stdout


@pytest.mark.parametrize("where", [(), ("--in-process",)], ids=["isolated", "in-process"])
# keep-a-target-s-own-failures-out-of-pyct-bugs-recurses-as-deep-as-plain-python
def test_a_recursion_plain_python_runs_runs_under_pyct(where: tuple[str, ...]) -> None:
    depth = int(_plain(_PLAIN_DEPTH)) - 20

    result = run_pyct(DEEP, "--args", json.dumps({"n": depth}), "--budget", "3", *where)

    assert result.returncode == 0, result.stderr[-2000:]
    assert first_line(result.stdout)["failure"] is None, first_line(result.stdout)["failure"]
