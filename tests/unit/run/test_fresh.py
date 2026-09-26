"""One input in a fresh interpreter, for real: each test starts a new Python."""

import os
import subprocess
import time
from pathlib import Path

import pytest

from pyct.execution.execute import ExecutionContext, execute
from pyct.results.failure import Failure, FailureKind
from pyct.run import fresh
from pyct.run.fresh import _journal, _request, in_a_fresh_interpreter, main
from pyct.run.journal import read
from pyct.run.process import KILL_GRACE, InputStartError
from pyct.run.target import load_target

ONE_CHECK = "targets.flip.one_check::classify"
SEGFAULT = "targets.isolate.segfault::fault"
SWALLOWS_ALARM = "targets.isolate.swallows_alarm::swallow"
BASE_RAISES = "targets.isolate.base_raises::stop"


def test_a_fresh_interpreter_runs_the_call_as_pyct_s_process_would() -> None:
    target = load_target(ONE_CHECK)
    ctx = ExecutionContext(fn=target.fn, file=target.file)

    fresh = in_a_fresh_interpreter(target.spec, target.file, {"x": 3}, None)

    assert fresh == execute(ctx, {"x": 3})


def test_a_fresh_interpreter_ends_the_way_its_call_did() -> None:
    target = load_target(SEGFAULT)

    fresh = in_a_fresh_interpreter(target.spec, target.file, {"x": 7, "y": 0}, None)

    assert fresh.failure == Failure(kind=FailureKind.CRASHED, detail="killed by SIGSEGV")
    assert [branch.taken for branch in fresh.branches] == [False, True]


def test_a_fresh_interpreter_is_alone_in_its_process() -> None:
    target = load_target(BASE_RAISES)

    fresh = in_a_fresh_interpreter(target.spec, target.file, {"x": 5, "y": 0}, None)

    assert fresh.failure == Failure(kind=FailureKind.TARGET_RAISED, detail="KeyboardInterrupt")


@pytest.mark.usefixtures("deadline_fires_in_a_child")
def test_a_fresh_interpreter_past_the_deadline_is_killed() -> None:
    target = load_target(SWALLOWS_ALARM)
    started = time.monotonic()

    fresh = in_a_fresh_interpreter(target.spec, target.file, {"x": 5}, started + 0.2)

    assert fresh.failure == Failure(kind=FailureKind.TIMEOUT, detail="deadline passed")
    assert time.monotonic() - started < 0.2 + KILL_GRACE + 0.5


def test_a_fresh_interpreter_that_cannot_start_is_an_input_that_could_not_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = load_target(ONE_CHECK)

    def refuse(*args: object, **kwargs: object) -> int:
        raise BlockingIOError(35, "Resource temporarily unavailable")

    monkeypatch.setattr(os, "posix_spawn", refuse)

    with pytest.raises(InputStartError, match="Resource temporarily unavailable"):
        in_a_fresh_interpreter(target.spec, target.file, {"x": 3}, None)


def test_arguments_a_fresh_interpreter_cannot_be_handed_are_an_input_that_could_not_start() -> None:
    target = load_target(ONE_CHECK)

    with pytest.raises(InputStartError, match="could not hand the input"):
        in_a_fresh_interpreter(target.spec, target.file, {"x": lambda: 3}, None)


def test_the_new_interpreter_s_side_runs_the_input_it_is_handed() -> None:
    target = load_target(ONE_CHECK)

    # fresh.main in a child forked here, as the new interpreter would run it
    with (
        _journal() as (journal, buffer),
        _request(target.spec, target.file, {"x": 3}, None) as request,
    ):
        pid = os.fork()
        if pid == 0:
            main(request, journal)
        os.waitpid(pid, 0)
        reading = read(buffer)

    assert reading.ended
    assert reading.end is None
    assert [branch.taken for branch in reading.branches] == [True]


def test_a_journal_file_that_cannot_be_sized_is_an_input_that_could_not_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = load_target(ONE_CHECK)

    def refuse(fd: int, length: int) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "ftruncate", refuse)

    with pytest.raises(InputStartError, match="No space left on device"):
        in_a_fresh_interpreter(target.spec, target.file, {"x": 3}, None)


def test_a_fresh_interpreter_that_dies_before_the_call_is_a_pyct_bug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = load_target(ONE_CHECK)
    # a boot that fails before pyct's side of the new interpreter is up
    monkeypatch.setattr(fresh, "_BOOT", "raise SystemExit(1)")

    result = in_a_fresh_interpreter(target.spec, target.file, {"x": 3}, None)

    assert result.failure == Failure(
        kind=FailureKind.PYCT_BUG,
        detail="the input's process ended before its call began: exited with code 1",
    )


def test_a_module_in_the_working_directory_does_not_break_the_boot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = load_target(ONE_CHECK)
    ctx = ExecutionContext(fn=target.fn, file=target.file)
    # named like a module of the standard library that pyct's own import needs
    (tmp_path / "token.py").write_text("SHADOWED = True\n")
    monkeypatch.chdir(tmp_path)

    fresh_result = in_a_fresh_interpreter(target.spec, target.file, {"x": 3}, None)

    assert fresh_result == execute(ctx, {"x": 3})


def test_a_fresh_interpreter_runs_with_pyct_s_own_interpreter_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = load_target("targets.isolate.asserts::check")
    # as if pyct ran under python -O
    monkeypatch.setattr(subprocess, "_args_from_interpreter_flags", lambda: ["-O"])

    fresh_result = in_a_fresh_interpreter(target.spec, target.file, {"x": 3}, None)

    assert fresh_result.failure is None
