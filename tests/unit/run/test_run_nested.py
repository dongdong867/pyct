"""run() with seeds only a caller can give: a seed that holds itself, and keys JSON cannot hold."""

import pytest

from pyct.results.record import StopKind
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.target import load_target

# where an input runs, in a child process of its own or in the caller's
WHERE = [Isolation.FORK, Isolation.IN_PROCESS]

# deeper than pickle recurses before it gives up, and within what JSON reads
PICKLE_DEPTH = 9000


@pytest.mark.parametrize("isolation", WHERE)
def test_run_walks_a_list_that_holds_itself_once(isolation: Isolation) -> None:
    xs: list[object] = [0]
    xs.append(xs)
    target = load_target("targets.nested.holds_itself::check")

    result = run(target, {"xs": xs}, isolation=isolation)

    assert [record.failure for record in result.records] == [None, None]
    assert result.stopped.reason == "no fork to flip"
    solved = result.records[1].args["xs"]
    assert isinstance(solved, list)
    assert isinstance(solved[0], int) and solved[0] > 5
    assert solved[1] is solved


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
