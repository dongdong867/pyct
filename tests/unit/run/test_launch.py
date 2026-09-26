"""The command in a process of its own, watched by the process the shell started.

Each test forks this process for real. The command's process never returns into the test
runner: every command here ends its process itself. The watcher's own end by a signal is
recorded instead of raised, so the test runner outlives it.
"""

import contextlib
import os
import signal
import threading
from collections.abc import Callable, Generator
from typing import NoReturn

import pytest

from pyct.run.launch import ImportWatch, launch

MODULE = "some.module"
ARGV = ["run", f"{MODULE}::f", '{"x": 1}']


@pytest.fixture(autouse=True)
def _handlers_kept() -> Generator[None]:
    """Put back the handlers the watcher takes or resets for the signals these tests send."""
    kept = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
    yield
    for number, handler in kept.items():
        signal.signal(number, handler)


@pytest.fixture
def raised(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """The signals the watcher raises on itself, recorded instead of raised."""
    signals: list[int] = []
    monkeypatch.setattr(signal, "raise_signal", signals.append)
    return signals


def ending_in(command: Callable[[ImportWatch | None], None]) -> Callable[[ImportWatch | None], int]:
    """``command`` in the command's process, which then exits 0 if the command did not end it."""

    def run(watch: ImportWatch | None) -> NoReturn:
        # a raise here must not unwind into the test runner's frames this process copied
        with contextlib.suppress(BaseException):
            command(watch)
        os._exit(0)

    return run


def exits_while_importing(watch: ImportWatch | None) -> None:
    assert watch is not None
    with watch.importing(MODULE):
        os._exit(3)


def is_killed_while_importing(watch: ImportWatch | None) -> None:
    assert watch is not None
    with watch.importing(MODULE):
        os.kill(os.getpid(), signal.SIGKILL)


def exits_after_importing(watch: ImportWatch | None) -> None:
    assert watch is not None
    with watch.importing(MODULE):
        pass
    os._exit(5)


def is_signaled_after_importing(watch: ImportWatch | None) -> None:
    assert watch is not None
    with watch.importing(MODULE):
        pass
    os.kill(os.getpid(), signal.SIGUSR1)


def test_an_exit_while_importing_names_the_module_and_the_exit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = launch(ending_in(exits_while_importing), ARGV)

    assert code == 1
    assert capsys.readouterr().err == f"cannot import {MODULE}: exited with code 3\n"


def test_a_signal_while_importing_names_the_module_and_the_signal(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = launch(ending_in(is_killed_while_importing), ARGV)

    assert code == 1
    assert capsys.readouterr().err == f"cannot import {MODULE}: killed by SIGKILL\n"


def test_an_exit_after_the_import_is_the_command_s_own(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = launch(ending_in(exits_after_importing), ARGV)

    assert code == 5
    assert capsys.readouterr().err == ""


def test_a_command_that_never_imports_ends_with_its_own_code() -> None:
    def leaves(watch: ImportWatch | None) -> None:
        os._exit(2)

    assert launch(ending_in(leaves), ARGV) == 2


def test_a_signal_after_the_import_ends_the_watcher_the_same_way(
    raised: list[int], capsys: pytest.CaptureFixture[str]
) -> None:
    code = launch(ending_in(is_signaled_after_importing), ARGV)

    assert raised == [signal.SIGUSR1]
    # what a shell reports, had the signal not ended the watcher
    assert code == 128 + signal.SIGUSR1
    assert capsys.readouterr().err == ""


def signal_once_ready(ready: int, go: int, number: int) -> None:
    """Send the main thread ``number`` once the command's process is ready, then let it go on."""
    os.read(ready, 1)
    signal.pthread_kill(threading.main_thread().ident or 0, number)
    os.write(go, b"!")


def signaled_while_importing(
    number: int, ending: Callable[[], None]
) -> Callable[[ImportWatch | None], int]:
    """A command that, while importing, lets the watcher get ``number``, then ends by ``ending``.

    A thread of this test sends the watcher the signal, aimed at the main
    thread, where the watcher waits.
    """
    ready, running = os.pipe()
    waiting, go = os.pipe()
    sender = threading.Thread(target=signal_once_ready, args=(ready, go, number), daemon=True)
    sender.start()

    def command(watch: ImportWatch | None) -> None:
        assert watch is not None
        with watch.importing(MODULE):
            os.write(running, b"!")
            os.read(waiting, 1)
            ending()

    return ending_in(command)


def dies_by_sigint() -> None:
    """How a Ctrl-C ends a process whose SIGINT takes its default action."""
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    os.kill(os.getpid(), signal.SIGINT)


def waits_for_sigterm() -> None:
    signal.pause()


def test_a_ctrl_c_while_importing_ends_the_watcher_as_the_command_s_process_ended(
    raised: list[int], capsys: pytest.CaptureFixture[str]
) -> None:
    # the terminal sends a Ctrl-C to both processes; each gets its own here
    code = launch(signaled_while_importing(signal.SIGINT, dies_by_sigint), ARGV)

    assert raised == [signal.SIGINT]
    assert code == 128 + signal.SIGINT
    assert capsys.readouterr().err == ""


def test_a_sigterm_to_the_watcher_goes_on_to_the_command_s_process(
    raised: list[int], capsys: pytest.CaptureFixture[str]
) -> None:
    # the command's process waits for a signal only the watcher can pass on
    code = launch(signaled_while_importing(signal.SIGTERM, waits_for_sigterm), ARGV)

    assert raised == [signal.SIGTERM]
    assert code == 128 + signal.SIGTERM
    assert capsys.readouterr().err == ""


def test_the_command_runs_in_this_process_when_no_other_can_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refused() -> int:
        raise BlockingIOError(35, "Resource temporarily unavailable")

    monkeypatch.setattr(os, "fork", refused)
    held = signal.pthread_sigmask(signal.SIG_BLOCK, set())

    code = launch(lambda watch: 7 if watch is None else 0, ARGV)

    assert code == 7
    assert signal.pthread_sigmask(signal.SIG_BLOCK, set()) == held


def test_the_page_names_the_module_only_while_it_imports() -> None:
    watch = ImportWatch(ARGV)

    assert watch.module() is None
    with pytest.raises(RuntimeError), watch.importing(MODULE):
        assert watch.module() == MODULE
        raise RuntimeError("the import raised")
    assert watch.module() is None


@pytest.mark.parametrize(
    "module",
    [
        pytest.param("m" * 20_000, id="longer-than-a-page"),
        pytest.param("modulé.ünïcode", id="more-bytes-than-characters"),
    ],
)
def test_the_page_holds_any_module_the_command_line_gives(module: str) -> None:
    watch = ImportWatch(["run", f"{module}::f"])

    with watch.importing(module):
        assert watch.module() == module
