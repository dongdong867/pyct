"""The command in a process of its own, watched by the process the shell started.

Each test forks this process for real. The command's process never returns into the test
runner: every command here ends its process itself. The watcher's own end by a signal is
recorded instead of raised, so the test runner outlives it.
"""

import os
import signal
import threading
import time
from collections.abc import Callable, Generator
from typing import NoReturn

import pytest

from pyct.run.import_watch import ImportWatch
from pyct.run.launch import Stopped, _stop_if_alone, launch

MODULE = "some.module"
ARGV = ["run", f"{MODULE}::f", '{"x": 1}']


# every signal these tests send, or the watcher takes a handler for
SIGNALS = (
    signal.SIGINT,
    signal.SIGTERM,
    signal.SIGHUP,
    signal.SIGUSR1,
    signal.SIGUSR2,
    signal.SIGALRM,
)


@pytest.fixture(autouse=True)
def _handlers_kept() -> Generator[None]:
    """Put back the handlers the watcher takes or resets for the signals these tests send."""
    kept = {number: signal.getsignal(number) for number in SIGNALS}
    yield
    for number, handler in kept.items():
        signal.signal(number, handler)


@pytest.fixture
def raised(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """The signals the watcher raises on itself, recorded instead of raised.

    The watcher is this test's own process. A process forked from it raises
    for real, so a command's process still ends by its signal.
    """
    signals: list[int] = []
    watcher = os.getpid()
    raise_for_real = signal.raise_signal

    def raise_signal(number: int) -> None:
        if os.getpid() == watcher:
            signals.append(number)
        else:
            raise_for_real(number)

    monkeypatch.setattr(signal, "raise_signal", raise_signal)
    return signals


def ending_in(command: Callable[[ImportWatch | None], None]) -> Callable[[ImportWatch | None], int]:
    """``command`` in the command's process, which then exits 0 if the command did not end it.

    A raise must not unwind into the test runner's frames this process
    copied. ``Stopped`` goes on, since the command's process catches it and
    ends by SIGTERM.
    """

    def run(watch: ImportWatch | None) -> NoReturn:
        try:
            command(watch)
        except Stopped:
            raise
        except BaseException:
            pass
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
    """Send the main thread ``number`` once the command's process is ready, then let it go on.

    An end of file on ``ready`` means the command's process never got ready,
    and the test is over, so nothing is sent.
    """
    if os.read(ready, 1) != b"!":
        return
    signal.pthread_kill(threading.main_thread().ident or 0, number)
    os.write(go, b"!")


type Signaled = Callable[[int, Callable[[], None]], Callable[[ImportWatch | None], int]]


@pytest.fixture
def signaled_while_importing() -> Generator[Signaled]:
    """Commands that, while importing, let the watcher get a signal, then end by ``ending``.

    A thread of this test sends the watcher the signal, aimed at the main
    thread, where the watcher waits. Each pipe is closed and each thread
    joined once the test ends: the write end the thread waits on goes
    first, so a thread still waiting reads its end and stops.
    """
    pipes: list[tuple[int, int]] = []
    senders: list[threading.Thread] = []

    def command_for(number: int, ending: Callable[[], None]) -> Callable[[ImportWatch | None], int]:
        ready, running = os.pipe()
        waiting, go = os.pipe()
        pipes.extend([(ready, running), (waiting, go)])
        sender = threading.Thread(target=signal_once_ready, args=(ready, go, number), daemon=True)
        sender.start()
        senders.append(sender)

        def command(watch: ImportWatch | None) -> None:
            assert watch is not None
            with watch.importing(MODULE):
                os.write(running, b"!")
                os.read(waiting, 1)
                ending()

        return ending_in(command)

    yield command_for
    close_and_join(pipes, senders)


def close_and_join(pipes: list[tuple[int, int]], senders: list[threading.Thread]) -> None:
    """Close each pipe's write end, join each sender, then close each read end."""
    for _, write_end in pipes:
        os.close(write_end)
    for sender in senders:
        sender.join(timeout=5)
        assert not sender.is_alive()
    for read_end, _ in pipes:
        os.close(read_end)


def dies_by_sigint() -> None:
    """How a Ctrl-C ends a process whose SIGINT takes its default action."""
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    os.kill(os.getpid(), signal.SIGINT)


def waits_for_sigterm() -> None:
    signal.pause()


def test_a_ctrl_c_while_importing_ends_the_watcher_as_the_command_s_process_ended(
    signaled_while_importing: Signaled, raised: list[int], capsys: pytest.CaptureFixture[str]
) -> None:
    # the terminal sends a Ctrl-C to both processes; each gets its own here
    code = launch(signaled_while_importing(signal.SIGINT, dies_by_sigint), ARGV)

    assert raised == [signal.SIGINT]
    assert code == 128 + signal.SIGINT
    assert capsys.readouterr().err == ""


def exits() -> None:
    os._exit(3)


def test_an_exit_while_importing_is_reported_though_the_watcher_got_a_signal(
    signaled_while_importing: Signaled, capsys: pytest.CaptureFixture[str]
) -> None:
    # the watcher notes the SIGINT, but the command's process ends by its own exit
    code = launch(signaled_while_importing(signal.SIGINT, exits), ARGV)

    assert code == 1
    assert capsys.readouterr().err == f"cannot import {MODULE}: exited with code 3\n"


def test_a_sigterm_to_the_watcher_goes_on_to_the_command_s_process(
    signaled_while_importing: Signaled, raised: list[int], capsys: pytest.CaptureFixture[str]
) -> None:
    # the command's process waits for a signal only the watcher can pass on
    code = launch(signaled_while_importing(signal.SIGTERM, waits_for_sigterm), ARGV)

    assert raised == [signal.SIGTERM]
    assert code == 128 + signal.SIGTERM
    assert capsys.readouterr().err == ""


def no_process_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused() -> int:
        raise BlockingIOError(35, "Resource temporarily unavailable")

    monkeypatch.setattr(os, "fork", refused)


def test_a_sigterm_ends_the_command_by_sigterm_and_puts_its_handler_back(
    monkeypatch: pytest.MonkeyPatch, raised: list[int]
) -> None:
    # with no process of its own, the command's process is this one, so its end is recorded
    no_process_starts(monkeypatch)
    before = signal.getsignal(signal.SIGTERM)

    def stopped(watch: ImportWatch | None) -> int:
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(5)
        return 0

    code = launch(stopped, ARGV)

    assert raised == [signal.SIGTERM]
    assert code == 128 + signal.SIGTERM
    assert signal.getsignal(signal.SIGTERM) is before


def outlasts_the_grace() -> None:
    """Wait with SIGINT at its default action, so a SIGINT passed on ends the process by it."""
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    time.sleep(5)
    os._exit(9)


def test_a_sigint_the_watcher_got_alone_goes_on_after_a_grace(
    signaled_while_importing: Signaled, raised: list[int], capsys: pytest.CaptureFixture[str]
) -> None:
    started = time.monotonic()
    code = launch(signaled_while_importing(signal.SIGINT, outlasts_the_grace), ARGV)

    # the command's process got no SIGINT of its own, so the watcher's reached it
    assert raised == [signal.SIGINT]
    assert code == 128 + signal.SIGINT
    assert time.monotonic() - started < 2
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("number", [signal.SIGHUP, signal.SIGUSR1, signal.SIGUSR2])
def test_a_signal_that_ends_a_process_goes_on_at_once(
    number: int, signaled_while_importing: Signaled, raised: list[int]
) -> None:
    code = launch(signaled_while_importing(number, outlasts_the_grace), ARGV)

    assert raised == [number]
    assert code == 128 + number


def test_the_command_runs_in_this_process_when_no_other_can_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    no_process_starts(monkeypatch)
    held = signal.pthread_sigmask(signal.SIG_BLOCK, set())

    code = launch(lambda watch: 7 if watch is None else 0, ARGV)

    assert code == 7
    assert signal.pthread_sigmask(signal.SIG_BLOCK, set()) == held


def test_the_lifeline_stops_the_command_s_process_once_the_watcher_is_gone() -> None:
    lifeline, kept = os.pipe()
    os.set_blocking(lifeline, False)
    try:
        # the watcher still holds its end: nothing to read yet, so the process goes on
        _stop_if_alone(lifeline)
        # nor is a byte an end of file, though the watcher never writes one
        os.write(kept, b"!")
        _stop_if_alone(lifeline)
        os.close(kept)
        with pytest.raises(Stopped):
            _stop_if_alone(lifeline)
    finally:
        os.close(lifeline)
