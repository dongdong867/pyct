import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from pyct.run.process import Waited
from pyct.sweep.process import run_command, waited_of

# a command that sleeps an hour
SLEEPS = "import time\ntime.sleep(3600)\n"


def python(script: str) -> list[str]:
    return [sys.executable, "-c", script]


def running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_a_command_ends_with_its_code_and_what_it_wrote(tmp_path: Path) -> None:
    script = (
        "import os, sys\n"
        "print(os.getcwd(), os.environ['SWEEP_TEST'])\n"
        "print('said', file=sys.stderr)\n"
        "sys.exit(3)\n"
    )
    env = {**os.environ, "SWEEP_TEST": "given"}
    finished = run_command(python(script), cwd=tmp_path, env=env, limit=30)

    assert finished.waited == Waited(signal=None, code=3)
    assert finished.stdout == f"{os.path.realpath(tmp_path)} given\n"
    assert finished.stderr == "said\n"


def test_a_command_a_signal_ends_says_which(tmp_path: Path) -> None:
    script = "import os, signal\nos.kill(os.getpid(), signal.SIGSEGV)\n"
    finished = run_command(python(script), cwd=tmp_path, env=dict(os.environ), limit=30)

    assert finished.waited == Waited(signal=signal.SIGSEGV, code=None)


def test_a_command_still_running_at_its_limit_is_stopped_with_what_it_started(
    tmp_path: Path,
) -> None:
    pids = tmp_path / "pids"
    script = (
        "import subprocess, sys, time\n"
        "started = subprocess.Popen(['/bin/sleep', '3600'])\n"
        f"open({str(pids)!r}, 'w').write(f'{{started.pid}}\\n')\n"
        "time.sleep(3600)\n"
    )
    began = time.monotonic()
    finished = run_command(python(script), cwd=tmp_path, env=dict(os.environ), limit=1.5)

    assert finished.waited is None
    assert time.monotonic() - began < 10
    started = int(pids.read_text())
    deadline = time.monotonic() + 5
    while running(started) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not running(started)


def test_a_return_code_reads_as_the_ending_pyct_run_words() -> None:
    assert waited_of(-signal.SIGKILL) == Waited(signal=signal.SIGKILL, code=None)
    assert waited_of(0) == Waited(signal=None, code=0)


# starts a command with SIGHUP at its default, whatever the test runner got, as under nohup
WITH_SIGHUP = (
    "import os, signal, sys\n"
    "signal.signal(signal.SIGHUP, signal.SIG_{action})\n"
    "os.execv(sys.executable, [sys.executable, *sys.argv[1:]])\n"
)


def test_an_ignored_sighup_stays_ignored() -> None:
    # under nohup the terminal's SIGHUP is ignored, and sweep must not start heeding it; a
    # process of its own, so a sweep that did heed it ends that process and not the tests
    check = (
        "import os, signal\n"
        "from pyct.sweep.process import hangup_stops_children\n"
        "with hangup_stops_children():\n"
        "    os.kill(os.getpid(), signal.SIGHUP)\n"
        "print(signal.getsignal(signal.SIGHUP) is signal.SIG_IGN)\n"
    )
    finished = subprocess.run(
        [sys.executable, "-c", WITH_SIGHUP.format(action="IGN"), "-c", check],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert (finished.returncode, finished.stdout) == (0, "True\n"), finished.stderr


def test_a_sighup_in_the_block_unwinds_it_and_ends_the_process_by_the_sighup() -> None:
    check = (
        "import os, signal\n"
        "from pyct.sweep.process import hangup_stops_children\n"
        "with hangup_stops_children():\n"
        "    try:\n"
        "        os.kill(os.getpid(), signal.SIGHUP)\n"
        "    finally:\n"
        "        print('unwound', flush=True)\n"
        "print('went on', flush=True)\n"
    )
    finished = subprocess.run(
        [sys.executable, "-c", WITH_SIGHUP.format(action="DFL"), "-c", check],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert (finished.returncode, finished.stdout) == (-signal.SIGHUP, "unwound\n")


def test_a_ctrl_c_as_a_command_starts_still_stops_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # the Ctrl-C comes just after the process starts, before sweep has recorded it
    real = subprocess.Popen
    children: list[subprocess.Popen[bytes]] = []

    def popen(*args: Any, **options: Any) -> subprocess.Popen[bytes]:
        children.append(real(*args, **options))
        signal.raise_signal(signal.SIGINT)
        return children[-1]

    monkeypatch.setattr(subprocess, "Popen", popen)
    try:
        with pytest.raises(KeyboardInterrupt):
            run_command(python(SLEEPS), cwd=tmp_path, env=dict(os.environ), limit=30)
        assert children[0].returncode == -signal.SIGKILL
    finally:
        children[0].kill()
        children[0].wait()


def test_a_command_starts_with_no_signal_held_that_sweep_held_while_starting_it(
    tmp_path: Path,
) -> None:
    script = "import signal\nprint(sorted(signal.pthread_sigmask(signal.SIG_BLOCK, [])))\n"
    finished = run_command(python(script), cwd=tmp_path, env=dict(os.environ), limit=30)

    assert finished.stdout == "[]\n"


def test_a_command_that_cannot_start_raises_and_holds_no_signal_after(tmp_path: Path) -> None:
    before = signal.pthread_sigmask(signal.SIG_BLOCK, [])

    with pytest.raises(FileNotFoundError):
        run_command([str(tmp_path / "missing")], cwd=tmp_path, env=dict(os.environ), limit=30)
    assert signal.pthread_sigmask(signal.SIG_BLOCK, []) == before
