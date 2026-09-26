"""Coverage for the input processes pyct forks inside the test process.

pyct ends each input's child process with ``os._exit``, taken when
``pyct.run.child`` is imported, and coverage.py saves nothing there by
itself. In every child this process forks, this hook points that exit at
one that stops coverage.py's measurement and saves it first, so the lines
a child ran count toward the suite's coverage.

A child whose deadline fires measures nothing. coverage.py's tracer takes
a lock from Python, a SIGALRM raised inside it can leave that lock held,
and the child would then hang on it until pyct kills it, which changes the
child's line. A test whose deadline fires in a child takes the
``deadline_fires_in_a_child`` fixture.

Without coverage.py measuring in this process, the hook imports nothing
and changes nothing.
"""

import contextlib
import os
import sys
from collections.abc import Iterator
from typing import NoReturn

import pytest

# what makes coverage.py start in a new process, or restart in a forked one
COVERAGE_STARTUP = ("COVERAGE_PROCESS_CONFIG", "COVERAGE_PROCESS_START")

_EXIT = os._exit

# whether the children forked from here measure; the fixture turns it off for one test
_measured = True


def _current() -> object | None:
    """The coverage.py measurement running in this process, or None. Imports nothing."""
    coverage = sys.modules.get("coverage")
    if coverage is None:
        return None
    return coverage.Coverage.current()  # pyrefly: ignore[missing-attribute]


def _saving_exit(status: int) -> NoReturn:
    """The input's process's exit, saving coverage.py's measurement first."""
    measuring = _current()
    if measuring is not None:
        with contextlib.suppress(Exception):
            measuring.stop()  # pyrefly: ignore[missing-attribute]
            measuring.save()  # pyrefly: ignore[missing-attribute]
    _EXIT(status)


def _after_fork_in_child() -> None:
    measuring = _current()
    if measuring is None:
        return
    if not _measured:
        measuring.stop()  # pyrefly: ignore[missing-attribute]
        return
    child = sys.modules.get("pyct.run.child")
    if child is not None:
        child._EXIT = _saving_exit  # pyrefly: ignore[missing-attribute]


os.register_at_fork(after_in_child=_after_fork_in_child)


@pytest.fixture
def deadline_fires_in_a_child(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep coverage.py out of every child this test forks, since their deadline fires."""
    monkeypatch.setattr(sys.modules[__name__], "_measured", False)
    for name in COVERAGE_STARTUP:
        monkeypatch.delenv(name, raising=False)
    yield
