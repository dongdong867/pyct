"""run() on nested seeds: values only a caller can give, and what each input is handed, per mode."""

import threading
from collections.abc import Mapping

import pytest

from pyct.binding import walk
from pyct.results.record import Source, StopKind
from pyct.run import run as run_module
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.target import load_target

# where an input runs, in a child process of its own or in the caller's
WHERE = [Isolation.FORK, Isolation.IN_PROCESS]
# and in a fresh interpreter, which imports the target by name
EVERYWHERE = [*WHERE, Isolation.FRESH]

# deeper than pickle recurses before it gives up, and within what JSON reads
PICKLE_DEPTH = 9000


@pytest.mark.parametrize("isolation", WHERE)
def test_run_walks_a_list_that_holds_itself_once(isolation: Isolation) -> None:
    xs: list[object] = [0]
    xs.append(xs)
    target = load_target("targets.nested.holds_itself::check")

    result = run(target, {"xs": xs}, isolation=isolation)

    assert [record.failure for record in result.records[:2]] == [None, None]
    assert result.stopped.reason == "no fork to flip"
    # the answer that flips the item keeps the list holding itself
    solved = result.records[1].args["xs"]
    assert isinstance(solved, list)
    assert isinstance(solved[0], int) and solved[0] > 5
    assert solved[1] is solved


def test_run_never_changes_the_callers_seed_under_a_float_key() -> None:
    seed: dict[str, object] = {"items": [0], "table": {1.5: [0]}}
    target = load_target("targets.nested.float_key::touch")

    result = run(target, seed, isolation=Isolation.IN_PROCESS)

    # no input met the list an earlier one grew, and every line shows it as called
    assert all(record.failure is None for record in result.records)
    assert all(record.args["table"] == {1.5: [0]} for record in result.records)
    assert seed == {"items": [0], "table": {1.5: [0]}}


def test_run_stops_cleanly_on_a_seed_too_deep_to_hand_to_a_fresh_interpreter() -> None:
    # pickle recurses once per level, so a seed this deep cannot cross to a new interpreter,
    # while a child process of pyct's own inherits it as it is
    seed: dict[str, object] = {"a": 0}
    for _ in range(PICKLE_DEPTH - 1):
        seed = {"a": seed}
    target = load_target("targets.nested.deep::check")

    result = run(target, {"config": seed}, isolation=Isolation.FRESH)

    assert result.records == ()
    assert result.stopped.kind is StopKind.COULD_NOT_START
    assert result.stopped.detail is not None
    assert "fresh interpreter" in result.stopped.detail


def test_run_walks_the_seed_once_and_once_more_per_solver_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    walks: list[object] = []
    rebuilt = walk.Walk.rebuilt

    def counted(
        one: walk.Walk, seed: Mapping[str, object], checks: object = None
    ) -> dict[str, object]:
        walks.append(seed)
        return rebuilt(one, seed, checks)  # type: ignore[arg-type]

    monkeypatch.setattr(walk.Walk, "rebuilt", counted)
    target = load_target("targets.nested.two_items::classify")

    # each input's own walk, bind's, happens in the input's process and is not counted here
    result = run(target, {"items": [1, 2]}, isolation=Isolation.FORK)

    solved = [record for record in result.records if record.source is Source.SOLVER]
    assert len(solved) >= 2
    # the leaves once for the run, then the one rebuild that writes each answer and notes its
    # leaves, which a later answer on its path starts from
    assert len(walks) == 1 + len(solved)


@pytest.mark.parametrize("isolation", EVERYWHERE)
def test_run_hands_each_input_arguments_of_its_own(isolation: Isolation) -> None:
    # the target grows the list it reaches through the tuple, which is `a` itself
    x = [0]
    target = load_target("targets.nested.grows_through_tuple::grow")

    result = run(target, {"a": x, "b": (x,)}, isolation=isolation)

    assert all(record.failure is None for record in result.records)
    assert result.stopped.reason == "no fork to flip"
    assert x == [0]
    for record in result.records:
        a, b = record.args["a"], record.args["b"]
        assert isinstance(a, list) and isinstance(b, tuple)
        # the line shows the input as it was called, both paths on one list, without the None
        # the target appended
        assert None not in a and b[0] is a


@pytest.mark.parametrize("isolation", EVERYWHERE)
def test_run_passes_a_positional_only_parameter_by_position(isolation: Isolation) -> None:
    target = load_target("targets.nested.positional_only::check")

    result = run(target, {"value": "x"}, isolation=isolation)

    assert [record.failure for record in result.records] == [None, None]
    assert [record.args["value"] for record in result.records] == ["x", "abc"]


class Holder:
    """An object deepcopy refuses, for its lock, that holds a list the seed also passes."""

    def __init__(self, xs: list[int]) -> None:
        self.lock = threading.Lock()
        self.xs = xs


def test_run_copies_the_seed_before_the_seed_input_can_change_it() -> None:
    # the holder cannot be copied, so the target grows the caller's own list through it; the
    # run's copy of `a` was made before, and every input starts from that copy
    x = [0]
    target = load_target("targets.nested.holder::grow")

    result = run(target, {"a": x, "h": Holder(x)}, isolation=Isolation.IN_PROCESS)

    assert all(record.failure is None for record in result.records)
    starts = [record.args["a"] for record in result.records]
    assert all(isinstance(a, list) and None not in a for a in starts), starts


def test_run_lets_go_of_an_input_no_later_answer_can_start_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held: list[tuple[int, list[int]]] = []
    attempt = run_module._attempt

    def watched(call: object, inputs: dict[int, object], tree: object, *rest: object) -> object:
        held.append((tree.oldest, sorted(inputs)))  # type: ignore[attr-defined]
        return attempt(call, inputs, tree, *rest)  # type: ignore[arg-type]

    monkeypatch.setattr(run_module, "_attempt", watched)
    target = load_target("targets.nested.two_items::classify")

    run(target, {"items": [1, 2]}, isolation=Isolation.IN_PROCESS)

    assert len(held) > 2
    assert all(min(kept) >= oldest for oldest, kept in held), held
