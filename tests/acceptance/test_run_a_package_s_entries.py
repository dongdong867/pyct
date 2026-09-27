"""Acceptance tests for the run-a-package-s-entries story, one per criterion of sweep-a-package.

Every test spawns ``python -P -m pyct sweep ...``, which runs each entry as its own
``pyct run``, so every test needs cvc5 on PATH unless it swaps PATH for its own.
"""

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.acceptance.harness import (
    REPO_ROOT,
    run_pyct,
    summary_line,
    version_then_crashing_cvc5,
)
from tests.acceptance.sweeping import (
    FIXTURES,
    SWEEP,
    environment,
    row_named,
    rows,
    summary,
    sweep,
)

# the limits sweep passes each entry's pyct run with no flags
DEFAULT_LIMITS = ("--budget", "30", "--plateau", "5", "--solver-timeout", "10")


def fixture_file(module: str) -> Path:
    """The file a fixture module under ``targets`` is written in."""
    path = REPO_ROOT.joinpath(*module.split("."))
    return path / "__init__.py" if path.is_dir() else path.with_suffix(".py")


def line_of(path: Path, text: str) -> int:
    """The number of the one line of ``path`` that holds ``text``."""
    found = [n for n, line in enumerate(path.read_text().splitlines(), 1) if text in line]
    assert len(found) == 1, found
    return found[0]


def covered(row: dict[str, Any], path: Path) -> list[int]:
    run = row["run"]
    assert isinstance(run, dict), row
    return run["covered"].get(str(path), [])


def running(pid: int) -> bool:
    """Whether the process still runs. A zombie, ended but not yet reaped, has ended: on macOS a
    signal 0 still reaches it."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    state = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout.strip()
    return bool(state) and not state.startswith("Z")


def gone(pids: Path) -> bool:
    """Whether every process the pid file names has ended within a few seconds."""
    deadline = time.monotonic() + 5
    while any(running(int(pid)) for pid in pids.read_text().split()):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)
    return True


def killed(pids: Path) -> None:
    """SIGKILL every process the pid file names that is still there, so a failure leaks none."""
    for pid in pids.read_text().split() if pids.exists() else []:
        with contextlib.suppress(ProcessLookupError):
            os.kill(int(pid), signal.SIGKILL)


# sweep-a-package-runs-each-public-function
@pytest.mark.timeout(120)
def test_runs_each_public_function() -> None:
    shop = f"{FIXTURES}.shop"
    result = sweep(shop, timeout=110)

    assert result.returncode == 0, result.stderr
    found = [(row["module"], row["name"]) for row in rows(result.stdout)]
    expected = [(f"{shop}._parse", "parse_price"), (f"{shop}.prices", "discount")]
    assert found == [*expected, (f"{shop}.prices", "total")]
    for row in rows(result.stdout):
        assert row["status"] == "ran", row
        spec = f"{row['module']}::{row['name']}"
        alone = run_pyct(spec, "--args", json.dumps(row["seed"]), *DEFAULT_LIMITS)
        assert row["run"] == summary_line(alone.stdout), alone.stderr
    parse = row_named(result.stdout, f"{shop}._parse", "parse_price")
    assert list(parse["run"]["total"]) == [str(fixture_file(f"{shop}._parse"))]
    counts = summary(result.stdout)
    assert (counts["ran"], counts["skipped"], counts["failed"]) == (3, 0, 0)


# sweep-a-package-runs-a-class-as-its-constructor
def test_runs_a_class_as_its_constructor() -> None:
    cart = f"{FIXTURES}.cart"
    result = sweep(cart)

    assert result.returncode == 0, result.stderr
    row = row_named(result.stdout, cart, "Cart")
    assert (row["status"], row["seed"]) == ("ran", {"owner": ""})
    path = fixture_file(cart)
    both = {line_of(path, 'self.rights = "all"'), line_of(path, 'self.rights = "none"')}
    assert both <= set(covered(row, path))
    assert {row["name"] for row in rows(result.stdout)} == {"Cart"}


FILES = """import os


def a_write(n: int) -> int:
    with open("out.txt", "w") as file:
        file.write("x")
    if n > 0:
        return 1
    return 0


def b_read(n: int) -> int:
    if os.path.exists("out.txt"):
        return -1
    if n > 0:
        return 1
    return 0
"""


# sweep-a-package-runs-each-entry-in-a-fresh-directory
def test_runs_each_entry_in_a_fresh_directory(tmp_path: Path) -> None:
    start, temporary = tmp_path / "start", tmp_path / "tmp"
    start.mkdir()
    temporary.mkdir()
    (start / "files.py").write_text(FILES)
    result = sweep("files", cwd=start, env={"TMPDIR": str(temporary)})

    assert result.returncode == 0, result.stderr
    assert [row["status"] for row in rows(result.stdout)] == ["ran", "ran"]
    read = row_named(result.stdout, "files", "b_read")
    returns = line_of(start / "files.py", "return -1")
    assert returns not in covered(read, (start / "files.py").resolve())
    assert covered(read, (start / "files.py").resolve()), read
    assert not (start / "out.txt").exists()
    assert not list(temporary.rglob("out.txt"))


# sweep-a-package-runs-each-entry-in-a-fresh-directory: the entry's module still imports from the
# file the listing found, and nothing in the sweep's folder stands in for pyct
def test_a_pyct_package_in_the_sweeps_folder_does_not_stand_in_for_pyct(tmp_path: Path) -> None:
    (tmp_path / "files.py").write_text(FILES)
    (tmp_path / "pyct").mkdir()
    (tmp_path / "pyct" / "__init__.py").write_text("import sys\nsys.exit('a stand-in for pyct')\n")
    result = sweep("files", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert [row["status"] for row in rows(result.stdout)] == ["ran", "ran"], result.stdout


# sweep-a-package-runs-each-entry-in-a-fresh-directory: the directory is the entry's alone, but
# its substituted code goes to the one cache in the folder the sweep runs from
def test_two_entries_share_one_cache(tmp_path: Path) -> None:
    (tmp_path / "files.py").write_text(FILES)
    env = {name: value for name, value in environment().items() if name != "PYCT_CACHE_DIR"}
    result = subprocess.run(
        [*SWEEP, "files"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert [row["status"] for row in rows(result.stdout)] == ["ran", "ran"]
    # one entry per module path, so both runs kept files.py's code in the same place
    kept = (tmp_path / ".pyct_cache" / "substituted").glob("*/*")
    assert len(list(kept)) == 1


# sweep-a-package-tells-people-on-stderr
def test_tells_people_on_stderr() -> None:
    pair = f"{FIXTURES}.pair"
    result = sweep(pair)

    assert result.returncode == 0, result.stderr
    path = fixture_file(pair)
    first, second = (row_named(result.stdout, pair, name) for name in ("first", "second"))
    union = set(covered(first, path)) | set(covered(second, path))
    total = first["run"]["total"][str(path)]
    assert result.stderr.splitlines() == [
        f'running {pair}::first {{"n": 0}} (1 of 2)',
        told(pair, first),
        f'running {pair}::second {{"n": 0}} (2 of 2)',
        told(pair, second),
        f"skipped {pair}::third: no parameter to vary",
        "swept 3 entries: 2 ran, 1 skipped, 0 failed",
        f"covered {len(union)} of {total} lines in 1 file",
        "stopped: done",
    ]


def told(module: str, row: dict[str, Any]) -> str:
    """The stderr line after a row that ran."""
    run = row["run"]
    assert isinstance(run, dict), row
    lines = sum(len(lines) for lines in run["covered"].values())
    total = sum(run["total"].values())
    stopped = run["stopped"]
    return f"ran {module}::{row['name']}: covered {lines} of {total} lines, stopped: {stopped}"


# sweep-a-package-warns-in-its-help
def test_warns_in_its_help() -> None:
    result = sweep("--help")

    assert result.returncode == 0, result.stderr
    said = " ".join(result.stdout.split())
    assert "calls every function and class it runs with inputs it made up" in said
    assert "Each entry runs in a temporary working directory" in said
    assert "which takes only the files an input writes by a relative path" in said
    assert "Nothing undoes a file an input writes anywhere else or a request it sends" in said


# sweep-a-package-sums-coverage-by-file
def test_sums_coverage_by_file() -> None:
    pair = f"{FIXTURES}.pair"
    result = sweep(pair)

    assert result.returncode == 0, result.stderr
    path = fixture_file(pair)
    first, second = (row_named(result.stdout, pair, name) for name in ("first", "second"))
    assert set(covered(first, path)) != set(covered(second, path))
    totals = summary(result.stdout)
    assert totals["covered"] == {
        str(path): sorted(set(covered(first, path)) | set(covered(second, path)))
    }
    assert totals["total"] == first["run"]["total"] == second["run"]["total"]


# sweep-a-package-runs-every-seed-it-writes
@pytest.mark.timeout(120)
def test_runs_every_seed_it_writes() -> None:
    given = {
        f"{FIXTURES}.seeds": {"f"},
        f"{FIXTURES}.defaults": {"f", "g"},
        f"{FIXTURES}.seeds_as_text": {"f", "g", "with_defaults"},
    }
    for module, functions in given.items():
        result = sweep(module, timeout=100)

        assert result.returncode == 0, result.stderr
        for name in functions:
            row = row_named(result.stdout, module, name)
            assert row["status"] == "ran", row


# sweep-a-package-passes-its-limits
@pytest.mark.timeout(120)
def test_passes_its_limits() -> None:
    spin = f"{FIXTURES}.spin"
    plain = sweep(spin, timeout=55)
    given = sweep(spin, "--budget", "20", "--plateau", "3", "--solver-timeout", "1", timeout=55)

    assert plain.returncode == 0, plain.stderr
    assert given.returncode == 0, given.stderr
    expected = {"budget": 30.0, "plateau": 5, "solver_timeout": 10.0, "total_budget": None}
    assert summary(plain.stdout)["limits"] == expected
    assert row_named(plain.stdout, spin, "spin")["run"]["stopped"] == "no gain in 5 inputs"
    expected = {"budget": 20.0, "plateau": 3, "solver_timeout": 1.0, "total_budget": None}
    assert summary(given.stdout)["limits"] == expected
    assert row_named(given.stdout, spin, "spin")["run"]["stopped"] == "no gain in 3 inputs"


# sweep-a-package-spends-the-total-budget
def test_spends_the_total_budget() -> None:
    sleepy = f"{FIXTURES}.sleepy"
    began = time.monotonic()
    # the first entry's deadline fires, so coverage.py stays out
    result = sweep(sleepy, "--budget", "10", "--total-budget", "3", measured=False)
    took = time.monotonic() - began

    assert result.returncode == 0, result.stderr
    first, *others = rows(result.stdout)
    assert (first["name"], first["status"], first["run"]["stopped"]) == ("a", "ran", "budget spent")
    assert [(row["name"], row["status"], row["seed"]) for row in others] == [
        ("b", "skipped", {"n": 0}),
        ("c", "skipped", {"n": 0}),
    ]
    assert {row["reason"] for row in others} == {"the sweep's total budget was spent"}
    totals = summary(result.stdout)
    assert totals["stopped"] == "total budget spent"
    assert totals["limits"]["total_budget"] == 3.0
    assert took < 6, took


# sweep-a-package-fails-a-run-with-no-summary
def test_fails_a_run_with_no_summary(tmp_path: Path) -> None:
    crash = f"{FIXTURES}.later.crash"
    result = sweep(crash, env={"SWEEP_IMPORTS_FILE": str(tmp_path / "imports")})

    assert result.returncode == 0, result.stderr
    again = row_named(result.stdout, f"{crash}.again", "price")
    assert (again["status"], again["run"]) == ("failed", None)
    assert again["reason"] == f"exit 1: cannot import {crash}.again: killed by SIGSEGV"
    assert row_named(result.stdout, f"{crash}.zeta", "last")["status"] == "ran"


# sweep-a-package-keeps-the-summary-of-a-failed-run
def test_keeps_the_summary_of_a_failed_run(tmp_path: Path) -> None:
    forks = f"{FIXTURES}.forks"
    version_then_crashing_cvc5(tmp_path)
    result = sweep(forks, env={"PATH": str(tmp_path)})

    row = row_named(result.stdout, forks, "sign")
    assert row["status"] == "failed", row
    assert row["run"]["stopped"] == "solver failed"
    assert row["reason"].startswith("exit 1: "), row


# sweep-a-package-stops-a-run-past-its-budget
@pytest.mark.timeout(180)
def test_stops_a_run_past_its_budget(tmp_path: Path) -> None:
    hang = f"{FIXTURES}.later.hang"
    pids = tmp_path / "pids"
    env = {"SWEEP_IMPORTS_FILE": str(tmp_path / "imports"), "SWEEP_PIDS_FILE": str(pids)}
    try:
        result = sweep(hang, "--budget", "1", env=env, timeout=170)

        assert result.returncode == 0, result.stderr
        again = row_named(result.stdout, f"{hang}.again", "price")
        assert (again["status"], again["run"]) == ("failed", None)
        assert again["reason"] == "stopped 60 s past its budget"
        assert gone(pids)
        assert row_named(result.stdout, f"{hang}.zeta", "last")["status"] == "ran"
    finally:
        killed(pids)


# pyct run's words for each limit it refuses, and sweep's for the rest
REFUSED = [
    ((), "the following arguments are required: PACKAGE"),
    (("shop/",), "PACKAGE must be a module name, got 'shop/'"),
    (("shop.py",), "PACKAGE must be a module name, got 'shop.py'"),
    (("shop", "--budget", "0"), ("--budget", "0")),
    (("shop", "--plateau", "2.5"), ("--plateau", "2.5")),
    (("shop", "--in-process"), "unrecognized arguments: --in-process"),
]


# sweep-a-package-refuses-a-bad-command-line
@pytest.mark.parametrize(("argv", "problem"), REFUSED)
def test_refuses_a_bad_command_line(argv: tuple[str, ...], problem: str | tuple[str, str]) -> None:
    result = sweep(*argv, cwd=REPO_ROOT / "targets" / "sweep")

    assert (result.returncode, result.stdout) == (2, ""), result.stderr
    words = refusal_of_run(*problem) if isinstance(problem, tuple) else problem
    assert words in result.stderr


def refusal_of_run(*limit: str) -> str:
    """The line ``pyct run`` refuses ``limit`` with."""
    refused = run_pyct(f"{FIXTURES}.forks::sign", "--args", '{"n": 0}', *limit)
    assert refused.returncode == 2, refused.stderr
    return refused.stderr.splitlines()[0]


# sweep-a-package-refuses-a-bad-command-line: the total budget, in the budget's words
def test_refuses_a_total_budget_the_budget_would_refuse() -> None:
    result = sweep("shop", "--total-budget", "nan", cwd=REPO_ROOT / "targets" / "sweep")

    assert (result.returncode, result.stdout) == (2, ""), result.stderr
    assert f"total {refusal_of_run('--budget', 'nan')}" in result.stderr


# sweep-a-package-needs-cvc5-to-run
def test_needs_cvc5_to_run(tmp_path: Path) -> None:
    forks = f"{FIXTURES}.forks"
    result = sweep(forks, env={"PATH": str(tmp_path)})
    alone = run_pyct(f"{forks}::sign", "--args", '{"n": 0}', path=str(tmp_path))

    assert (result.returncode, result.stdout) == (1, ""), result.stderr
    assert alone.returncode == 1, alone.stderr
    assert result.stderr == alone.stderr


# starts a command with SIGHUP at its default, whatever the test runner got, as under a terminal
WITH_SIGHUP_AT_DEFAULT = (
    "import os, signal, sys\n"
    "signal.signal(signal.SIGHUP, signal.SIG_DFL)\n"
    "os.execv(sys.executable, [sys.executable, *sys.argv[1:]])\n"
)


@contextlib.contextmanager
def interrupted_sweep(pids: Path) -> Iterator[subprocess.Popen[str]]:
    """``pyct sweep`` on the interrupted fixture, in a session of its own as a terminal's
    foreground group, once its sleeping entry has started. Nothing it names outlives the test."""
    env = environment({"SWEEP_PIDS_FILE": str(pids)})
    process = subprocess.Popen(
        [sys.executable, "-c", WITH_SIGHUP_AT_DEFAULT, *SWEEP[1:], f"{FIXTURES}.interrupted"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 30
        while not (pids.exists() and pids.read_text().endswith("\n")):
            assert time.monotonic() < deadline, "the sleeping entry never started"
            time.sleep(0.05)
        yield process
    finally:
        # macOS refuses a group whose only member has exited unreaped
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        killed(pids)


# sweep-a-package-ends-on-ctrl-c
def test_ends_on_ctrl_c(tmp_path: Path) -> None:
    pids = tmp_path / "pids"
    with interrupted_sweep(pids) as process:
        # a Ctrl-C reaches the terminal's foreground group, the sweep's processes, and no other
        os.killpg(process.pid, signal.SIGINT)
        stdout, stderr = process.communicate(timeout=20)

        assert process.returncode == -signal.SIGINT, stderr
        assert stderr.splitlines()[-1] == "KeyboardInterrupt", stderr
        lines = [json.loads(line) for line in stdout.splitlines()]
        assert [(line["name"], line["status"]) for line in lines] == [("a_main", "skipped")]
        assert gone(pids)


# sweep-a-package-ends-on-ctrl-c: a SIGTERM, or the SIGHUP a closing terminal sends, to the pid
# the shell got ends every process the sweep started, and the sweep by that signal
@pytest.mark.parametrize("number", [signal.SIGTERM, signal.SIGHUP])
def test_ends_on_a_sigterm_or_a_sighup(tmp_path: Path, number: int) -> None:
    pids = tmp_path / "pids"
    with interrupted_sweep(pids) as process:
        process.send_signal(number)
        stdout, stderr = process.communicate(timeout=20)

        assert process.returncode == -number, stderr
        lines = [json.loads(line) for line in stdout.splitlines()]
        assert [(line["name"], line["status"]) for line in lines] == [("a_main", "skipped")]
        assert gone(pids)
