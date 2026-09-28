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
import mmap
import os
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from pyct.core.branch import Branch, Site
from pyct.execution.execute import ExecutionResult
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import DowngradeCount
from pyct.run.journal import NUMBER, RECORDS, JournalWriter
from pyct.run.journal_reader import JournalReader
from pyct.run.process import ending, watched
from tests.acceptance.harness import COVERAGE_STARTUP, REPO_ROOT, input_lines, run_pyct
from tests.acceptance.test_strs import forks_of
from tests.acceptance.timed import Measured, within

COUNTDOWN = "targets.loops.countdown::count_down"
FOREVER = json.dumps({"x": 100_000_000})

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


SITE = Site(file="t.py", line=3, col=7)
FORK = Branch(expression=["<", "x", ["+", "y", 1]], taken=True, site=SITE)
# long enough for pyct's process to look at the journal in between
_PAUSE = 0.05


def _input_writing(size: int, write: Callable[[mmap.mmap, JournalWriter], None]) -> ExecutionResult:
    """What pyct makes of an input whose process runs ``write`` into a journal of ``size`` bytes.

    pyct's process looks at the journal while the process writes, and reads
    the rest once it has ended, as it does for every input it forks.
    """
    with mmap.mmap(-1, size) as buffer:
        reader = JournalReader(buffer)

        def start() -> int:
            pid = os.fork()
            # coverage.py cannot see the child's lines: they run in a frame begun before the fork
            if pid == 0:  # pragma: no cover
                try:
                    write(buffer, JournalWriter(buffer))
                finally:
                    sys.stdout.flush()
                    os._exit(0)
            return pid

        waited = watched(start, None, reader.look)
        return ending(reader.finish(), waited)


def _facts_before(writer: JournalWriter, pause: float = _PAUSE) -> None:
    """The facts before the problem, with a pause after each so pyct looks at them."""
    writer.start()
    writer.line(2)
    writer.fork(FORK)
    time.sleep(pause)
    for count in range(1, 4):
        writer.downgrade("__xor__", SITE, count)
        time.sleep(pause)


def _committed_after_the_facts_before() -> int:
    """Where the facts before the problem end, as the same facts written again lay them out."""
    scratch = bytearray(RECORDS + 4096)
    _facts_before(JournalWriter(scratch), pause=0)
    return int.from_bytes(scratch[0:8], sys.byteorder)


_BEFORE_LINES = frozenset({2})
_BEFORE_DOWNGRADES = (DowngradeCount("__xor__", 3, SITE),)


# read-an-input-s-journal-within-its-second-keeps-a-journal-problem
def test_a_full_journal_ends_its_input_as_a_pyct_bug_with_the_facts_before() -> None:
    def fills(buffer: mmap.mmap, writer: JournalWriter) -> None:
        _facts_before(writer)
        for line in range(3, 10_000):
            writer.line(line)
        time.sleep(_PAUSE)
        writer.end(None)

    size = RECORDS + 4096
    result = _input_writing(size, fills)

    assert result.failure == Failure(FailureKind.PYCT_BUG, f"the journal is full at {size} bytes")
    assert result.branches == (FORK,)
    assert result.downgrades == _BEFORE_DOWNGRADES
    assert result.lines > _BEFORE_LINES
    assert max(result.lines) < 10_000


# read-an-input-s-journal-within-its-second-keeps-a-journal-problem
def test_an_unreadable_record_ends_its_input_as_a_pyct_bug_with_the_facts_before() -> None:
    at = _committed_after_the_facts_before()

    def breaks(buffer: mmap.mmap, writer: JournalWriter) -> None:
        _facts_before(writer)
        # a record of a kind the journal has none of, committed as a whole, then looked at
        writer._record(99, NUMBER.pack(99))
        time.sleep(_PAUSE)
        writer.line(100)
        writer.end(None)

    result = _input_writing(RECORDS + 4096, breaks)

    assert result.failure == Failure(
        FailureKind.PYCT_BUG, f"could not read the input's facts at byte {at}"
    )
    assert result.branches == (FORK,)
    assert result.downgrades == _BEFORE_DOWNGRADES
    assert result.lines == _BEFORE_LINES
