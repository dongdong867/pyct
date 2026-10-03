"""``close``: a guest's block gives back what it borrowed however its frame ended.

Each test runs in pytest's process, where pyct is a guest, so each block borrows SIGALRM's
handler and starts a watcher thread; none of them fires its alarm.
"""

import signal
import threading
import time
import types
from contextlib import AbstractContextManager
from pathlib import Path

import pytest

from pyct.execution import execute as execute_module
from pyct.execution.deadline import close, deadline
from pyct.execution.execute import ExecutionContext, execute


def watchers() -> list[str]:
    return [thread.name for thread in threading.enumerate() if thread.name == "pyct deadline"]


def test_closing_a_block_whose_exit_a_raise_skipped_gives_the_handler_back() -> None:
    previous = signal.getsignal(signal.SIGALRM)
    block = deadline(time.monotonic() + 60)
    # a block entered and never exited, as when a raise lands before its __exit__
    block.__enter__()
    borrowed = signal.getsignal(signal.SIGALRM)

    close(block)
    close(block)

    assert borrowed is not previous
    assert signal.getsignal(signal.SIGALRM) is previous
    assert watchers() == []


def test_closing_a_block_that_set_nothing_changes_nothing() -> None:
    previous = signal.getsignal(signal.SIGALRM)

    close(deadline(None))

    assert signal.getsignal(signal.SIGALRM) is previous


def _own(signal_number: int, frame: types.FrameType | None) -> None:
    """A handler of the program's own, which ``close`` must leave alone."""


def test_closing_a_block_never_entered_leaves_the_handler_alone() -> None:
    previous = signal.signal(signal.SIGALRM, _own)
    try:
        # a Ctrl-C between the block's making and its entry: it never read the handler
        close(deadline(time.monotonic() + 60))
        after = signal.getsignal(signal.SIGALRM)
    finally:
        signal.signal(signal.SIGALRM, previous)

    assert after is _own


def test_closing_a_block_that_exited_leaves_a_later_handler_alone() -> None:
    previous = signal.getsignal(signal.SIGALRM)
    block = deadline(time.monotonic() + 60)
    with block:
        pass
    signal.signal(signal.SIGALRM, _own)
    try:
        close(block)
        after = signal.getsignal(signal.SIGALRM)
    finally:
        signal.signal(signal.SIGALRM, previous)

    assert after is _own


def skipped_exit(ctx: object, bound: object, block: AbstractContextManager[None]) -> object:
    """A call whose block a raise left without its ``__exit__``."""
    block.__enter__()
    raise RuntimeError("raised before the block's exit")


def test_a_raise_as_the_line_tracer_stops_still_closes_the_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    previous = signal.getsignal(signal.SIGALRM)
    stop = execute_module._LineTracer.stop

    def failing(tracer: execute_module._LineTracer) -> None:
        stop(tracer)
        raise RuntimeError("the line tracer's stop failed")

    monkeypatch.setattr(execute_module._LineTracer, "stop", failing)
    monkeypatch.setattr(execute_module, "_call", skipped_exit)
    ctx = ExecutionContext(fn=lambda: None, file=str(tmp_path / "none.py"))

    with pytest.raises(RuntimeError, match="stop failed"):
        execute(ctx, {}, time.monotonic() + 60)

    assert signal.getsignal(signal.SIGALRM) is previous
    assert watchers() == []
