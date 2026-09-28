"""A parallel run holds the ``serial`` group back until every other test is done."""

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.serial_last import SerialLastScheduling

REPO_ROOT = Path(__file__).resolve().parents[1]

COLLECTION = ["t.py::a", "t.py::s1@serial", "t.py::b", "t.py::c", "t.py::s2@serial", "t.py::d"]


@dataclass(eq=False)
class Worker:
    """A worker as xdist runs one: it holds its last test until more work or its shutdown comes.

    ``sent`` is every test it was sent, each as its place in the collection.
    """

    sent: list[int] = field(default_factory=list)
    queue: list[int] = field(default_factory=list)
    shutting_down: bool = False
    gateway: SimpleNamespace = field(default_factory=lambda: SimpleNamespace(id="gw"))

    def send_runtest_some(self, indexes: list[int]) -> None:
        self.sent.extend(indexes)
        self.queue.extend(indexes)

    def shutdown(self) -> None:
        self.shutting_down = True

    def running(self) -> int | None:
        if len(self.queue) >= 2 or (self.shutting_down and self.queue):
            return self.queue[0]
        return None


def scheduling(workers: list[Worker], collection: list[str]) -> SerialLastScheduling:
    """The scheduler of a run whose workers each collected ``collection``, work handed out."""
    config = SimpleNamespace(
        getvalue=lambda name: [f"{len(workers)}*popen"] if name == "tx" else None,
        option=SimpleNamespace(loadscopereorder=False),
    )
    scheduler = SerialLastScheduling(config)  # pyrefly: ignore[bad-argument-type]
    for worker in workers:
        scheduler.add_node(worker)  # pyrefly: ignore[bad-argument-type]
        scheduler.add_node_collection(worker, collection)  # pyrefly: ignore[bad-argument-type]
    scheduler.schedule()
    return scheduler


def run_to_the_end(scheduler: SerialLastScheduling, workers: list[Worker]) -> list[set[int]]:
    """Each worker runs a test a round, as the scheduler directs; the tests of each round."""
    rounds = []
    while any(worker in scheduler.assigned_work for worker in workers):
        assert len(rounds) < 100, rounds
        if scheduler.tests_finished:
            for worker in workers:
                worker.shutdown()
        running = {worker: worker.running() for worker in workers}
        rounds.append({test for test in running.values() if test is not None})
        for worker, test in running.items():
            if test is not None:
                worker.queue.pop(0)
                scheduler.mark_test_complete(worker, test)  # pyrefly: ignore[bad-argument-type]
        for worker in workers:
            if worker.shutting_down and not worker.queue and worker in scheduler.assigned_work:
                scheduler.remove_node(worker)  # pyrefly: ignore[bad-argument-type]
    return rounds


def test_the_serial_group_starts_when_every_other_test_is_done() -> None:
    workers = [Worker(), Worker()]
    scheduler = scheduling(workers, COLLECTION)

    rounds = run_to_the_end(scheduler, workers)

    serial = {1, 4}
    first = next(n for n, running in enumerate(rounds) if running & serial)
    assert all(running <= serial for running in rounds[first:]), rounds
    assert set().union(*rounds[:first]) == {0, 2, 3, 5}
    assert sorted(i for worker in workers for i in worker.sent) == list(range(len(COLLECTION)))


def test_the_serial_group_runs_on_one_worker() -> None:
    workers = [Worker(), Worker(), Worker()]
    scheduler = scheduling(workers, COLLECTION)

    run_to_the_end(scheduler, workers)

    assert [worker for worker in workers if {1, 4} <= set(worker.sent)] != []


def test_a_run_of_only_serial_tests_starts_them_at_once() -> None:
    workers = [Worker(), Worker()]
    scheduler = scheduling(workers, ["t.py::s1@serial", "t.py::s2@serial"])

    rounds = run_to_the_end(scheduler, workers)

    assert rounds[0] == {0}
    assert [worker.sent for worker in workers if worker.sent] == [[0, 1]]


def crash_and_replace(
    scheduler: SerialLastScheduling, crashed: Worker
) -> tuple[int, str | None, Worker]:
    """``crashed`` finishes its first test and dies in its second; a new worker takes its place.

    The test it died in, what ``remove_node`` named, which xdist reports failed, and the new
    worker.
    """
    finished, running = crashed.queue[:2]
    crashed.queue.pop(0)
    scheduler.mark_test_complete(crashed, finished)  # pyrefly: ignore[bad-argument-type]
    crashitem = scheduler.remove_node(crashed)  # pyrefly: ignore[bad-argument-type]
    replacement = Worker()
    scheduler.add_node(replacement)  # pyrefly: ignore[bad-argument-type]
    scheduler.add_node_collection(replacement, COLLECTION)  # pyrefly: ignore[bad-argument-type]
    scheduler.schedule()
    return running, crashitem, replacement


def test_a_crashed_workers_test_is_named_and_runs_no_more() -> None:
    crashed, survivor = Worker(), Worker()
    scheduler = scheduling([crashed, survivor], COLLECTION)
    sent_before = len(survivor.sent)

    running, crashitem, replacement = crash_and_replace(scheduler, crashed)
    run_to_the_end(scheduler, [survivor, replacement])

    assert crashitem == COLLECTION[running]
    assert running not in survivor.sent[sent_before:] + replacement.sent


def test_every_other_test_runs_once_after_a_worker_crashed() -> None:
    crashed, survivor = Worker(), Worker()
    scheduler = scheduling([crashed, survivor], COLLECTION)

    running, _, replacement = crash_and_replace(scheduler, crashed)
    run_to_the_end(scheduler, [survivor, replacement])

    ran = crashed.sent[:1] + survivor.sent + replacement.sent
    assert sorted(ran) == [test for test in range(len(COLLECTION)) if test != running]


def test_a_worker_alone_after_a_crash_is_given_enough_to_run_what_was_left() -> None:
    crashed = Worker()
    scheduler = scheduling([crashed], COLLECTION)

    running, _, replacement = crash_and_replace(scheduler, crashed)
    run_to_the_end(scheduler, [replacement])

    ran = crashed.sent[:1] + replacement.sent
    assert sorted(ran) == [test for test in range(len(COLLECTION)) if test != running]


def test_a_worker_leaving_while_another_collects_leaves_the_rest_to_that_one() -> None:
    first, last = Worker(), Worker()
    scheduler = scheduling([first, last], COLLECTION)
    first_ran, crashitems = running_then_crashing(scheduler, first)
    collecting = Worker()
    scheduler.add_node(collecting)  # pyrefly: ignore[bad-argument-type]

    crashitems.append(scheduler.remove_node(last))  # pyrefly: ignore[bad-argument-type]
    scheduler.add_node_collection(collecting, COLLECTION)  # pyrefly: ignore[bad-argument-type]
    scheduler.schedule()
    run_to_the_end(scheduler, [collecting])

    left = [test for test, nodeid in enumerate(COLLECTION) if nodeid not in crashitems]
    assert sorted(first_ran + collecting.sent) == left


def running_then_crashing(
    scheduler: SerialLastScheduling, worker: Worker
) -> tuple[list[int], list[str | None]]:
    """``worker`` runs the tests it holds now, then dies; what it ran, and the test it died in."""
    ran = list(worker.queue)
    for test in ran:
        worker.queue.pop(0)
        scheduler.mark_test_complete(worker, test)  # pyrefly: ignore[bad-argument-type]
    return ran, [scheduler.remove_node(worker)]  # pyrefly: ignore[bad-argument-type]


# a run's tests: quick ones before and after one that ends its worker's process, and a serial
# group. The worker that dies has finished tests before it, as a worker lost near a run's end
# has, and may hold tests after it that it never starts
QUICK_TESTS = """
import time

import pytest


@pytest.mark.parametrize("n", range(6))
def test_quick(n):
    time.sleep(0.05)
"""
SERIAL_TESTS = """
import pytest


@pytest.mark.serial
@pytest.mark.parametrize("n", range(3))
def test_serial(n):
    pass
"""
# how the test in the middle ends its worker, a second after it notes that it started, so a
# second worker has run every other test and left by then
ENDS = {
    "exits": "time.sleep(1)\n    os._exit(1)",
    "times out": "time.sleep(3600)",
}


def write_a_run(folder: Path, end: str) -> Path:
    """The tests of a run in ``folder``, one ending as ``end`` says; the file it notes in."""
    for name in ("test_a_quick.py", "test_z_quick.py"):
        (folder / name).write_text(QUICK_TESTS)
    (folder / "test_serial.py").write_text(SERIAL_TESTS)
    started = folder / "started"
    (folder / "test_m_dies.py").write_text(
        "import os, time\n\n\ndef test_dies():\n"
        f"    with open({str(started)!r}, 'a') as started:\n        started.write('x')\n"
        f"    {ENDS[end]}\n"
    )
    return started


def run_in_workers(folder: Path, workers: int) -> subprocess.CompletedProcess[str]:
    """The project's pytest settings and scheduler on ``folder``, in ``workers`` workers.

    The timeout is cut to two seconds, and the run starts no coverage of this one.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("COVERAGE_")}
    env["PYTHONPATH"] = str(REPO_ROOT)
    config = str(REPO_ROOT / "pyproject.toml")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-c", config, "--rootdir", str(folder), "-n", str(workers)]
        + ["--confcutdir", str(folder), "-p", "tests.conftest", "-o", "timeout=2"]
        + ["--basetemp", str(folder / "base"), "-p", "no:cacheprovider"],
        cwd=folder,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=40,
    )


@pytest.mark.parametrize("workers", [1, 2])
@pytest.mark.parametrize("end", ENDS)
def test_a_run_ends_after_a_worker_dies(tmp_path: Path, end: str, workers: int) -> None:
    started_file = write_a_run(tmp_path, end)
    started = time.monotonic()

    result = run_in_workers(tmp_path, workers)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "FAILED test_m_dies.py::test_dies" in output
    assert output.count("PASSED test_serial.py::test_serial") == 3, output
    assert "15 passed" in output, output
    # the dead worker's test is not run again, on the worker that replaces it
    assert started_file.read_text() == "x"
    # two seconds of timeout, and the start and stop of the run and of the new worker
    assert time.monotonic() - started < 30
