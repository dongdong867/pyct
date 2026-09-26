"""run() puts each input in a process of its own, and stops when it cannot start one."""

import os

import pytest

from pyct.branches.tree import Tree
from pyct.results.record import Stop, StopKind
from pyct.run.process import InputStartError
from pyct.run.run import Bounds, _attempt, run
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
    assert run(target, {"x": 3}, isolated=False).environment.isolated is False


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
    tree.add(run(target, seed, isolated=False).records[0].forks)

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

    result = run(target, {"x": 3}, isolated=False)

    assert len(result.records) == 2
    assert result.stopped.kind is StopKind.NO_FORK
