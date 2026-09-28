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
from collections.abc import Callable, Iterator
from typing import NoReturn

import pytest
from xdist.remote import Producer
from xdist.scheduler import Scheduling

from tests.serial_last import SERIAL, SerialLastScheduling

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


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Put every test marked ``serial`` in the group a parallel run holds back until the end.

    First, so a worker names the group in each test's id before it sends the ids back.
    """
    for item in items:
        if item.get_closest_marker("serial") is not None:
            item.add_marker(pytest.mark.xdist_group(SERIAL))


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_make_scheduler(config: pytest.Config, log: Producer) -> Scheduling | None:
    """``--dist loadgroup`` runs the ``serial`` group last, alone; tests/serial_last.py."""
    if config.getvalue("dist") != "loadgroup":
        return None
    return SerialLastScheduling(config, log)


@pytest.fixture(autouse=True, scope="session")
def _session_cache(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Keep the code pyct substitutes for a target in a folder of this session's own.

    pyct keeps it in ``.pyct_cache`` in the folder it runs from, the repository
    root for most tests, unless ``PYCT_CACHE_DIR`` names another folder. Every
    run this session starts, and every run in this process, inherits the
    variable, so the suite writes nothing into the checkout.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("PYCT_CACHE_DIR", str(tmp_path_factory.mktemp("pyct-cache")))
        yield


@pytest.fixture(autouse=True)
def _forget_substituted_modules() -> Iterator[None]:
    """Drop, after each test, every module pyct substituted as it was imported.

    A test that calls ``main()`` in this process imports its target with the
    hook open, and the module would stay substituted for every later test,
    which expects the target as written, so the suite would depend on the
    order it runs in.
    """
    yield
    for name, module in list(sys.modules.items()):
        if type(getattr(module, "__loader__", None)).__module__ == "pyct.intercept.hook":
            del sys.modules[name]


@pytest.fixture
def coverage_paused() -> Iterator[None]:
    """Stop every coverage.py measurement this process runs for the test, then start each again.

    A parallel run's worker runs two: the one coverage.py starts in each process a measured
    process starts, and pytest-cov's above it. Stopping one resumes the one below, so pausing
    only pytest-cov's, as its ``no_cover`` mark does, leaves the test traced.
    """
    stopped = []
    while (measuring := _current()) is not None:
        measuring.stop()  # pyrefly: ignore[missing-attribute]
        stopped.append(measuring)
    yield
    for measuring in reversed(stopped):
        measuring.start()  # pyrefly: ignore[missing-attribute]


@pytest.fixture(autouse=True)
def _deadline_fires_only_when_marked(request: pytest.FixtureRequest) -> Iterator[None]:
    """Fail a test whose deadline fires in this process, unless it is marked ``DEADLINE_FIRES``.

    Under coverage, such a test can hang on coverage.py's lock until the per-test timeout ends
    its worker; tests/unit/deadline_fires.py. The raise is noted with coverage or without, so
    an unmarked test fails in every run, not only in the one it hangs. A child the test forks
    raises on its own and fails nothing here. Covers the tests whose module imported pyct's
    deadline before the test starts, as a test module does.
    """
    deadline = sys.modules.get("pyct.execution.deadline")
    if deadline is None or "coverage_paused" in request.fixturenames:
        yield
        return
    fired: list[int] = []
    raise_deadline: Callable[[int, object], NoReturn]
    raise_deadline = deadline._raise_deadline  # pyrefly: ignore[missing-attribute]
    tester = os.getpid()

    def noting(signal_number: int, frame: object) -> NoReturn:
        if os.getpid() == tester:
            fired.append(signal_number)
        raise_deadline(signal_number, frame)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(deadline, "_raise_deadline", noting)
        yield
    if fired:
        pytest.fail("the test fired its deadline in this process without DEADLINE_FIRES")


@pytest.fixture
def deadline_fires_in_a_child(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep coverage.py out of every child this test forks, since their deadline fires."""
    monkeypatch.setattr(sys.modules[__name__], "_measured", False)
    for name in COVERAGE_STARTUP:
        monkeypatch.delenv(name, raising=False)
    yield
