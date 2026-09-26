"""Acceptance tests for the run-a-target-in-a-throwaway-process story.

Each test spawns ``python -P -m pyct`` through the harness, because what the story
changes is where the target runs: a process of its own per input, which only a real
run through the command line starts from a clean interpreter. The closure test calls
``run()`` in a fresh interpreter of its own for the same reason.
"""

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from pyct.cli import main
from tests.acceptance.harness import (
    REPO_ROOT,
    input_lines,
    let_pyct_run_in_process,
    run_pyct,
    summary_line,
)

ISOLATE = REPO_ROOT / "targets" / "isolate"
COUNTER = "targets.isolate.counter::count"
COUNTER_FILE = ISOLATE / "counter.py"
PROCESS_STATE = "targets.isolate.process_state::disturb"
PROCESS_STATE_FILE = ISOLATE / "process_state.py"
CLOSURE_FILE = ISOLATE / "closure.py"
SEGFAULT = "targets.isolate.segfault::fault"
SEGFAULT_FILE = ISOLATE / "segfault.py"
EXITS = "targets.isolate.exits::leave"
ABORTS = "targets.isolate.aborts::give_up"
PRINTS = "targets.isolate.prints::speak"
READS_STDIN = "targets.isolate.reads_stdin::ask"
BASE_RAISES = "targets.isolate.base_raises::stop"
C_HANG = "targets.isolate.c_hang::stall"
C_HANG_FILE = ISOLATE / "c_hang.py"
SWALLOWS_ALARM = "targets.isolate.swallows_alarm::swallow"
# the budget these tests give, and how long after its start a run with it must have ended
BUDGET = "1"
ENDED_WITHIN = 4.0
# how soon after Ctrl-C pyct must have exited
EXITED_WITHIN = 2.0

# run() on a closure no module attribute names, printing what each record covered
RUN_A_CLOSURE = """
import inspect, json
from pyct.run.run import run
from pyct.run.target import Target
from targets.isolate.closure import make

count = make()
target = Target(
    spec="targets.isolate.closure::make",
    fn=count,
    file=count.__code__.co_filename,
    signature=inspect.signature(count),
)
result = run(target, {"x": 0})
print(json.dumps([[r.source.value, sorted(r.covered_lines)] for r in result.records]))
"""


def marked(file: Path) -> set[int]:
    """The lines a fixture marks as ones only an earlier input's leftovers can run."""
    lines = file.read_text().splitlines()
    return {number for number, text in enumerate(lines, start=1) if "# marked" in text}


def covered_in(line: dict[str, object], file: Path) -> set[int]:
    """The lines of ``file`` one printed line covered."""
    covered = line["covered"]
    assert isinstance(covered, dict), line
    return set(covered.get(str(file), []))


def environment_of(stdout: str) -> dict[str, object]:
    environment = summary_line(stdout)["environment"]
    assert isinstance(environment, dict), stdout
    return environment


# run-a-target-in-a-throwaway-process-starts-each-input-fresh
def test_starts_each_input_fresh() -> None:
    result = run_pyct(COUNTER, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert len(inputs) == 2, result.stdout
    assert all(not covered_in(line, COUNTER_FILE) & marked(COUNTER_FILE) for line in inputs)
    assert inputs[1]["source"] == "solver"
    assert inputs[1]["mismatch_at"] is None
    assert environment_of(result.stdout)["isolated"] is True


# run-a-target-in-a-throwaway-process-runs-in-process-on-request
def test_runs_in_process_on_request() -> None:
    result = run_pyct(COUNTER, '{"x": 0}', "--in-process")

    assert result.returncode == 0, result.stderr
    solver = input_lines(result.stdout)[1]
    assert solver["source"] == "solver"
    assert marked(COUNTER_FILE) <= covered_in(solver, COUNTER_FILE)
    assert environment_of(result.stdout)["isolated"] is False


# run-a-target-in-a-throwaway-process-resets-process-state
def test_resets_process_state() -> None:
    result = run_pyct(PROCESS_STATE, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert len(inputs) == 2, result.stdout
    for line in inputs:
        assert not covered_in(line, PROCESS_STATE_FILE) & marked(PROCESS_STATE_FILE), line


# run-a-target-in-a-throwaway-process-isolates-a-closure-through-run
def test_isolates_a_closure_through_run() -> None:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    finished = subprocess.run(
        [sys.executable, "-c", RUN_A_CLOSURE],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert finished.returncode == 0, finished.stderr
    records = json.loads(finished.stdout)
    assert [source for source, _ in records] == ["seed", "solver"]
    for _, covered in records:
        assert covered
        assert not set(covered) & marked(CLOSURE_FILE)


def line_with(file: Path, text: str) -> int:
    """The number of the one line of ``file`` that holds ``text``."""
    lines = file.read_text().splitlines()
    (number,) = [number for number, line in enumerate(lines, start=1) if text in line]
    return number


def solver_line(stdout: str) -> dict[str, object]:
    """The first solver input's line."""
    lines = input_lines(stdout)
    assert len(lines) > 1, stdout
    assert lines[1]["source"] == "solver", stdout
    return lines[1]


def fork_sides(line: dict[str, object]) -> list[tuple[object, bool]]:
    """Each fork on a line as its expression and the side the input took."""
    forks = line["forks"]
    assert isinstance(forks, list), line
    return [(fork["expression"], fork["taken"]) for fork in forks]


# run-a-target-in-a-throwaway-process-survives-a-segfault
def test_survives_a_segfault() -> None:
    result = run_pyct(SEGFAULT, '{"x": 0, "y": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    (crashed,) = [line for line in inputs if line["args"] == {"x": 7, "y": 0}]
    assert crashed["failure"] == {"kind": "crashed", "detail": "killed by SIGSEGV"}
    assert (["==", "x", 7], True) in fork_sides(crashed)
    assert line_with(SEGFAULT_FILE, "string_at") in covered_in(crashed, SEGFAULT_FILE)
    later = inputs[inputs.index(crashed) + 1 :]
    assert any(isinstance(line["args"], dict) and line["args"]["y"] > 3 for line in later)
    assert "stopped" in json.loads(result.stdout.splitlines()[-1])


# run-a-target-in-a-throwaway-process-reports-an-exit-without-raising
def test_reports_an_exit_without_raising() -> None:
    result = run_pyct(EXITS, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    assert solver_line(result.stdout)["failure"] == {
        "kind": "system_exit",
        "detail": "exited with code 3",
    }
    assert len(input_lines(result.stdout)) == 2, result.stdout


# run-a-target-in-a-throwaway-process-names-the-signal
def test_names_the_signal() -> None:
    result = run_pyct(ABORTS, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    assert solver_line(result.stdout)["failure"] == {
        "kind": "crashed",
        "detail": "killed by SIGABRT",
    }
    assert "ended crashed: killed by SIGABRT" in result.stderr.splitlines()


# run-a-target-in-a-throwaway-process-feeds-the-loop-from-a-crashed-seed
def test_feeds_the_loop_from_a_crashed_seed() -> None:
    result = run_pyct(SEGFAULT, '{"x": 7, "y": 0}')

    assert result.returncode == 0, result.stderr
    seed, solver, *_ = input_lines(result.stdout)
    assert seed["failure"] == {"kind": "crashed", "detail": "killed by SIGSEGV"}
    assert fork_sides(seed) == [([">", "y", 3], False), (["==", "x", 7], True)]
    aim = solver["aim"]
    assert isinstance(aim, dict), solver
    forks = seed["forks"]
    assert isinstance(forks, list)
    assert {"file": aim["file"], "line": aim["line"], "col": aim["col"]} in [
        {"file": fork["file"], "line": fork["line"], "col": fork["col"]} for fork in forks
    ]


# run-a-target-in-a-throwaway-process-keeps-stdout-for-lines
def test_keeps_stdout_for_lines() -> None:
    result = run_pyct(PRINTS, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    inputs = len(lines) - 1
    assert inputs == 2, result.stdout
    assert result.stderr.splitlines().count("hello") == inputs
    assert result.stderr.splitlines().count("raw") == inputs


# run-a-target-in-a-throwaway-process-gives-the-target-an-empty-stdin
def test_gives_the_target_an_empty_stdin() -> None:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    finished = subprocess.run(
        [sys.executable, "-P", "-m", "pyct", "run", READS_STDIN, '{"x": 0}'],
        cwd=REPO_ROOT,
        env=env,
        input="typed by a person\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert finished.returncode == 0, finished.stderr
    seed = input_lines(finished.stdout)[0]
    failure = seed["failure"]
    assert isinstance(failure, dict), seed
    assert failure["kind"] == "target_raised"
    assert str(failure["detail"]).startswith("EOFError"), failure


# run-a-target-in-a-throwaway-process-ends-a-hang-in-c-at-the-deadline
def test_ends_a_hang_in_c_at_the_deadline() -> None:
    started = time.monotonic()
    result = run_pyct(C_HANG, '{"x": 0}', "--budget", BUDGET)
    took = time.monotonic() - started

    assert result.returncode == 0, result.stderr
    solver = solver_line(result.stdout)
    assert solver["failure"] == {"kind": "timeout", "detail": "deadline passed"}
    reached = {line_with(C_HANG_FILE, "if x > 3"), line_with(C_HANG_FILE, "hangs in C")}
    assert reached <= covered_in(solver, C_HANG_FILE)
    assert summary_line(result.stdout)["stopped"] == "budget spent"
    assert took < ENDED_WITHIN, took


# run-a-target-in-a-throwaway-process-ends-a-target-that-swallows-the-alarm
def test_ends_a_target_that_swallows_the_alarm() -> None:
    started = time.monotonic()
    result = run_pyct(SWALLOWS_ALARM, '{"x": 0}', "--budget", BUDGET)
    took = time.monotonic() - started

    assert result.returncode == 0, result.stderr
    assert solver_line(result.stdout)["failure"] == {
        "kind": "timeout",
        "detail": "deadline passed",
    }
    assert summary_line(result.stdout)["stopped"] == "budget spent"
    assert took < ENDED_WITHIN, took


def pid_written_to(path: Path, process: subprocess.Popen[str]) -> int:
    """The pid the target wrote to ``path``, once it has; the run must still be going."""
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and process.poll() is None:
        with contextlib.suppress(FileNotFoundError, ValueError):
            return int(path.read_text())
        time.sleep(0.05)
    raise AssertionError(f"no pid in {path}; pyct exited {process.poll()}")


def is_running(pid: int) -> bool:
    """Whether ``pid`` names a process, after a moment for the system to reap an orphan."""
    for _ in range(20):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        time.sleep(0.05)
    return True


@contextlib.contextmanager
def pyct_in_a_session(spec: str, pid_file: Path) -> Iterator[subprocess.Popen[str]]:
    """``pyct run`` in a session of its own, so a SIGINT can reach its whole group.

    That is how a terminal sends Ctrl-C. Whatever is left of the run, and the
    input's process named in ``pid_file``, is killed on the way out.
    """
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYCT_TEST_PID_FILE"] = str(pid_file)
    process = subprocess.Popen(
        [sys.executable, "-P", "-m", "pyct", "run", spec, '{"x": 0}'],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        yield process
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        with contextlib.suppress(FileNotFoundError, ValueError, ProcessLookupError):
            os.kill(int(pid_file.read_text()), signal.SIGKILL)


# run-a-target-in-a-throwaway-process-leaves-no-process-behind-on-ctrl-c
def test_leaves_no_process_behind_on_ctrl_c(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    with pyct_in_a_session(C_HANG, pid_file) as process:
        child = pid_written_to(pid_file, process)
        sent = time.monotonic()
        os.killpg(process.pid, signal.SIGINT)
        stdout, stderr = process.communicate(timeout=10)
        took = time.monotonic() - sent

    assert took < EXITED_WITHIN, took
    # the way a Ctrl-C has always ended pyct: the interrupt's traceback, and its signal
    assert process.returncode == -signal.SIGINT, stderr
    assert "KeyboardInterrupt" in stderr
    assert all(json.loads(line) for line in stdout.splitlines()), stdout
    assert not is_running(child)


def fail_the_second_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let pyct start the seed's process, and refuse the next, however pyct starts it."""
    starts = [0]

    def refusing[**P](start: Callable[P, int]) -> Callable[P, int]:
        def attempt(*args: P.args, **kwargs: P.kwargs) -> int:
            starts[0] += 1
            if starts[0] == 2:
                raise BlockingIOError(35, "Resource temporarily unavailable")
            return start(*args, **kwargs)

        return attempt

    monkeypatch.setattr(os, "fork", refusing(os.fork))
    monkeypatch.setattr(os, "posix_spawn", refusing(os.posix_spawn))


# run-a-target-in-a-throwaway-process-stops-when-it-cannot-start-an-input
def test_stops_when_it_cannot_start_an_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    let_pyct_run_in_process(monkeypatch)
    fail_the_second_start(monkeypatch)

    code = main(["run", COUNTER, '{"x": 0}'])

    out, err = capsys.readouterr()
    assert code == 1
    (seed,) = input_lines(out)
    assert seed["source"] == "seed"
    assert summary_line(out)["stopped"] == "could not start an input"
    stopped = err.splitlines().index("stopped: could not start an input")
    assert "Resource temporarily unavailable" in err.splitlines()[stopped + 1]
    assert err.splitlines()[stopped + 1].startswith("    ")


def args_of(line: dict[str, object]) -> dict[str, int]:
    args = line["args"]
    assert isinstance(args, dict), line
    return args


def failure_of(line: dict[str, object]) -> dict[str, object]:
    failure = line["failure"]
    assert isinstance(failure, dict), line
    return failure


# run-a-target-in-a-throwaway-process-reports-a-base-exception-the-target-raises
def test_reports_a_base_exception_the_target_raises() -> None:
    result = run_pyct(BASE_RAISES, '{"x": 0, "y": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    interrupted = [line for line in inputs if args_of(line)["x"] > 3]
    halted = [line for line in inputs if args_of(line)["x"] <= 3 and args_of(line)["y"] > 3]
    assert interrupted and halted, result.stdout
    assert failure_of(interrupted[0]) == {"kind": "target_raised", "detail": "KeyboardInterrupt"}
    assert failure_of(halted[0])["kind"] == "target_raised"
    assert str(failure_of(halted[0])["detail"]).endswith("Halt: halted")
    assert "stopped" in json.loads(result.stdout.splitlines()[-1])
