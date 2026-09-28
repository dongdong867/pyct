"""run() on a `dict[int, X]` in each place an input runs: every one binds the annotation, so a
key pyct does not follow that may equal a made-up int turns the dict plain there too."""

import pytest

from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.target import load_target


@pytest.mark.parametrize("isolation", [Isolation.FORK, Isolation.IN_PROCESS, Isolation.FRESH])
def test_a_tracked_bool_key_leaves_no_answer_off_the_plan(isolation: Isolation) -> None:
    target = load_target("targets.dicts.int_equal_keys::tracked_bool")

    result = run(target, {"b": False, "d": {}}, isolation=isolation)

    assert [record.mismatch_at for record in result.records] == [None] * len(result.records)
    assert [entry.name for entry in result.records[0].downgrades] == ["__contains__"]
