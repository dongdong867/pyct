"""A parallel run holds the ``serial`` group back until every other test is done."""

from dataclasses import dataclass, field
from types import SimpleNamespace

from tests.serial_last import SerialLastScheduling

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
