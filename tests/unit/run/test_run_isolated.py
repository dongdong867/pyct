"""run() puts each input in a process of its own, and stops when it cannot start one."""

import os
import random

import pytest

from pyct.branches.tree import Tree
from pyct.results.coverage import Coverage
from pyct.results.record import InputRecord, Stop, StopKind
from pyct.run.isolation import Isolation
from pyct.run.process import InputStartError
from pyct.run.run import Bounds, Tell, _attempt, run
from pyct.run.target import load_target

REFUSED = "[Errno 35] Resource temporarily unavailable"


def refuse_every_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """No process can start, however pyct starts one."""

    def refuse(*args: object, **kwargs: object) -> int:
        raise BlockingIOError(35, "Resource temporarily unavailable")

    monkeypatch.setattr(os, "fork", refuse)
    monkeypatch.setattr(os, "posix_spawn", refuse)


def test_a_run_says_whether_it_isolated_its_inputs() -> None:
    target = load_target("targets.flip.one_check::classify")

    assert run(target, {"x": 3}).environment.isolated is True
    assert run(target, {"x": 3}, isolation=Isolation.IN_PROCESS).environment.isolated is False


def test_a_seed_that_cannot_start_stops_the_run_with_no_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = load_target("targets.flip.one_check::classify")
    refuse_every_start(monkeypatch)

    result = run(target, {"x": 3})

    assert result.records == ()
    assert result.stopped.kind is StopKind.COULD_NOT_START
    assert result.stopped.detail is not None
    assert REFUSED in result.stopped.detail
    assert result.coverage.covered == {target.file: frozenset()}


def test_an_input_that_cannot_start_stops_the_loop() -> None:
    target = load_target("targets.flip.one_check::classify")
    seed = {"x": 3}
    tree = Tree()
    tree.add(run(target, seed, isolation=Isolation.IN_PROCESS).records[0].forks)

    def refused(args: object, until: float | None) -> object:
        raise InputStartError(f"could not start a child process: {REFUSED}")

    attempt = _attempt(refused, seed, tree, Bounds(), ())  # pyrefly: ignore[bad-argument-type]

    assert attempt.record is None
    assert attempt.stop == Stop(
        kind=StopKind.COULD_NOT_START, detail=f"could not start a child process: {REFUSED}"
    )


def test_an_input_in_process_needs_no_process_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = load_target("targets.flip.one_check::classify")
    refuse_every_start(monkeypatch)

    result = run(target, {"x": 3}, isolation=Isolation.IN_PROCESS)

    assert len(result.records) == 2
    assert result.stopped.kind is StopKind.NO_FORK


def test_a_caller_drawing_from_random_between_inputs_moves_no_forked_input_s_draw() -> None:
    target = load_target("targets.isolate.seeded::draw")
    left = random.getstate()

    def draws(record: InputRecord, coverage: Coverage) -> None:
        random.random()

    result = run(target, {"x": 0}, isolation=Isolation.FORK, tell=Tell(report=draws))
    random.setstate(left)

    # the seed and the one input that flips its fork, each drawing as the import left random
    first_forks = [record.forks[0].expression for record in result.records]
    assert first_forks == [first_forks[0]] * 2
    assert result.stopped.kind is StopKind.NO_FORK
