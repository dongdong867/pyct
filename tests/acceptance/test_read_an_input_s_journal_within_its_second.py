"""Acceptance tests for read-an-input-s-journal-within-its-second.

The timed tests spawn ``python -P -m pyct`` on the countdown loop, which loops until its
deadline and records a fork on each pass, and measure each run from launch to exit. Each takes
the best of three runs (see ``tests.acceptance.timed``), so a slow moment of a loaded machine
fails no test and a run that is always late still does.

The lines a run prints are held against digests of what ``v2`` printed at b85bbc4a, which
62e9e5cd, the commit this change started from, prints too, with the paths and the environment
that differ between checkouts and machines taken out.
"""

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.core.branch import Branch
from pyct.results.failure import Failure, FailureKind
from pyct.run import isolation
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.target import load_target
from tests.acceptance.harness import COVERAGE_STARTUP, REPO_ROOT, forks_of, input_lines, run_pyct
from tests.acceptance.timed import Measured, within

COUNTDOWN = "targets.loops.countdown::count_down"
FOREVER = json.dumps({"x": 100_000_000})

# the journal the full-journal test gives each input, where 256 MiB takes seconds to fill
_SMALL_JOURNAL = 2 * 1024 * 1024

# the forks a run may list before each further 100,000 adds half a second to its bound
_FORKS_FREE = 100_000
_SECONDS_PER_FORKS = 0.5

# the Baseline's peak memory, from launch to exit, less the least it grew per fork: 31 MB with
# no fork, and 2.02 to 2.15 KB more for each fork on the seed's line in every run it measured
_BASELINE_START = 31e6
_BASELINE_PER_FORK = 2_000

_CUT = re.compile(r"cut the expressions of (\d+) forks, from position (\d+) on,")

# a target whose one input downgrades one operation many times over, long enough for pyct to
# look at its journal as the count grows, then downgrades another once and raises
_DOWNGRADES_THEN_RAISES = """\
def f(x: int) -> int:
    for i in range(300_000):
        c = x ^ i
    d = x ^ 5
    raise ValueError(f"stopped after {c} and {d}")
"""

# what each run printed at b85bbc4a and at 62e9e5cd alike: stdout's digest, then stderr's
_PRINTED = {
    "300": (
        "25b38bfb4ed33d76e9bbaf130671d1101abcc0b6ca578790337e87c54ad408da",
        "559fe1518c9f46ce3d589fc82a48409d2c637c337511d86a52b0d3f3576d0669",
    ),
    "2000": (
        "4c6327a2137d353bb212004689e6827d2a4db5eced3839566a9d2ad9404b6280",
        "4dea5348df62f6b41fe224d251ae9555cfe30f049d0351a6c8d3f06aa69a0456",
    ),
    "100000": (
        "058bb1f279351b931ac5313537306a8f62bc0866041c6721a2357d938917787a",
        "44b5be1336fdbe05052b8d3c06264074fe13914d0e2f45f139fb16144fe5f352",
    ),
    "downgrades": (
        "becff47e5cae3b959bc6bf7c7fdea3a7ce45be6e02526cc5dc5d5fa2d0327e2f",
        "7d5ccb5a680da358334c9f851ccd98c8e73f01cd70d3c7eda4ef9cd400d6881e",
    ),
}


def _bound(budget: float, forks: int) -> float:
    """The seconds from launch the criteria give a run of ``budget`` seconds that listed
    ``forks`` forks on its last input's line."""
    beyond = max(forks - _FORKS_FREE, 0)
    return budget + 1 + _SECONDS_PER_FORKS * beyond / _FORKS_FREE


def _forks(run: Measured) -> int:
    """The forks the seed's line lists, as its trace counts them past the line's budget."""
    found = _CUT.search(run.stderr)
    assert found is not None, run.stderr[-2000:]
    return int(found[1]) + int(found[2])


def _counting_down(budget: str, *more: str) -> list[str]:
    return [COUNTDOWN, "--args", FOREVER, "--budget", budget, *more]


def _within_its_bound(budget: float) -> Callable[[Measured], bool]:
    return lambda run: run.wall < _bound(budget, _forks(run))


@pytest.mark.serial
# read-an-input-s-journal-within-its-second-ends-the-one-second-countdown-within-a-second
def test_the_one_second_countdown_ends_within_a_second_of_its_budget(tmp_path: Path) -> None:
    run = within(tmp_path, _counting_down("1"), lambda measured: measured.wall < 2)

    assert run.returncode == 0, run.stderr[-2000:]
    assert run.wall < 2, run.wall
    seed = input_lines(run.stdout)[0]
    assert seed["failure"] == {"kind": "timeout", "detail": "deadline passed"}
    fork_lines = [line for line in run.stderr.splitlines() if line.startswith("fork ")]
    assert len(forks_of(seed)) == len(fork_lines) > 10_000
    assert run.stderr.splitlines()[-1] == "stopped: budget spent"
    assert run.peak_bytes <= 400e6, run.peak_bytes


@pytest.mark.serial
@pytest.mark.timeout(120)
@pytest.mark.parametrize("budget", [3, 5])
# read-an-input-s-journal-within-its-second-grows-slowly-past-a-hundred-thousand-forks
def test_a_longer_budget_ends_within_its_scaled_bound(tmp_path: Path, budget: int) -> None:
    run = within(tmp_path, _counting_down(str(budget)), _within_its_bound(budget))

    assert run.returncode == 0, run.stderr[-2000:]
    forks = _forks(run)
    assert run.wall < _bound(budget, forks), (run.wall, forks)
    assert run.peak_bytes <= 1.1 * (_BASELINE_START + _BASELINE_PER_FORK * forks), (
        run.peak_bytes,
        forks,
    )


@pytest.mark.serial
# read-an-input-s-journal-within-its-second-ends-in-process-as-isolated
def test_an_in_process_run_ends_within_the_same_bound(tmp_path: Path) -> None:
    run = within(tmp_path, _counting_down("1", "--in-process"), _within_its_bound(1))

    assert run.returncode == 0, run.stderr[-2000:]
    assert run.wall < _bound(1, _forks(run)), (run.wall, _forks(run))
    assert run.stderr.splitlines()[-1] == "stopped: budget spent"


def _printed(result_stdout: str, result_stderr: str, *roots: Path) -> tuple[str, str]:
    """The digests of what a run printed, its paths and its environment taken out."""

    def normalized(text: str) -> str:
        for root in roots:
            text = text.replace(str(root), "<root>")
        return text

    summary = json.loads(result_stdout.splitlines()[-1])
    stdout = result_stdout.replace(json.dumps(summary["environment"]), "<environment>")
    return _digest(normalized(stdout)), _digest(normalized(result_stderr))


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.mark.timeout(180)
@pytest.mark.parametrize("seed", [300, 2000, 100_000])
# read-an-input-s-journal-within-its-second-prints-what-it-printed
def test_a_countdown_prints_what_it_printed(seed: int) -> None:
    # no budget: one input past the seed covers nothing new, so the run ends by itself, and the
    # solver gets all the time its answer for a path of 100,000 forks takes
    result = run_pyct(
        COUNTDOWN,
        json.dumps({"x": seed}),
        "--plateau",
        "1",
        "--solver-timeout",
        "120",
        unset=COVERAGE_STARTUP,
        timeout=170,
    )

    assert result.returncode == 0, result.stderr[-2000:]
    assert _printed(result.stdout, result.stderr, REPO_ROOT) == _PRINTED[str(seed)]


# read-an-input-s-journal-within-its-second-prints-what-it-printed
def test_a_repeated_downgrade_that_raises_prints_what_it_printed(tmp_path: Path) -> None:
    (tmp_path / "downgrades_then_raises.py").write_text(_DOWNGRADES_THEN_RAISES)

    result = run_pyct("downgrades_then_raises::f", '{"x": 3}', cwd=tmp_path, unset=COVERAGE_STARTUP)

    assert result.returncode == 0, result.stderr[-2000:]
    assert _printed(result.stdout, result.stderr, tmp_path) == _PRINTED["downgrades"]


# read-an-input-s-journal-within-its-second-keeps-a-journal-problem
def test_a_full_journal_ends_its_input_as_a_pyct_bug_with_the_forks_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a journal of 2 MiB, which the countdown fills after thousands of passes, while pyct looks
    monkeypatch.setattr(isolation, "CAPACITY", _SMALL_JOURNAL)
    target = load_target(COUNTDOWN)

    # forked, as the command line forks it: the test's own timeout thread would move it to a
    # fresh interpreter
    result = run(target, {"x": 100_000}, limits=Limits(budget=Budget(3)), isolation=Isolation.FORK)

    seed = result.records[0]
    assert seed.failure == Failure(
        FailureKind.PYCT_BUG, f"the journal is full at {_SMALL_JOURNAL} bytes"
    )
    assert 1_000 < len(seed.forks) < 100_000, len(seed.forks)
    assert _counts_down(seed.forks)
    assert seed.covered_lines >= {2, 3}, sorted(seed.covered_lines)


def _counts_down(forks: tuple[Branch, ...]) -> bool:
    """Whether the forks are the countdown's passes in order, each taken: `x > 0`, then on each
    pass the value before it less one, `["-", before, 1] > 0`."""
    before: object = None
    for fork in forks:
        match fork.expression:
            case [">", "x", 0] if before is None:
                before = "x"
            case [">", ["-", held, 1] as value, 0] if held is before or held == before == "x":
                before = value
            case _:
                return False
    return all(fork.taken for fork in forks)
