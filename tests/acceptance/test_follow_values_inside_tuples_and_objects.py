"""Acceptance tests for the follow-values-inside-tuples-and-objects child of the
run-with-nested-arguments story.

Each test calls ``run()``, since only a caller in Python can hand pyct a tuple, an object, or
one value under two names. A test about copies runs in a child process and in pyct's own,
where an input that changed the caller's value would show it to the next one.
"""

import json

import pytest

from pyct.config.goal import Goal
from pyct.config.limits import Limits
from pyct.results.record import InputRecord, StopKind
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.target import load_target
from targets.nested import objects

# where an input runs, in a child process of its own or in the caller's
WHERE = [Isolation.FORK, Isolation.IN_PROCESS]


def compares(record: InputRecord) -> list[tuple[str, bool]]:
    """The record's forks that compare a value with a number, each as JSON text with its side,
    in order: those on a length left out."""
    return [
        (json.dumps(fork.expression), fork.taken)
        for fork in record.forks
        if isinstance(fork.expression, list)
        and fork.expression[0] == ">"
        and isinstance(fork.expression[1], list)
        and fork.expression[1][0] != "len"
    ]


def above(value: object, bound: int) -> bool:
    """Whether a value is an int above ``bound``."""
    return isinstance(value, int) and not isinstance(value, bool) and value > bound


# run-with-nested-arguments-keeps-an-alias-one-value
@pytest.mark.parametrize("isolation", WHERE)
def test_keeps_an_alias_one_value(isolation: Isolation) -> None:
    shared = [0]
    target = load_target("targets.nested.aliases::two_paths")

    result = run(target, {"a": shared, "b": shared}, isolation=isolation)

    a_0 = ["[]", "a", 0]
    named = {expression for record in result.records for expression, _ in compares(record)}
    assert named == {json.dumps([">", a_0, 5]), json.dumps([">", a_0, 7])}, named
    both = [
        record
        for record in result.records
        if [taken for _, taken in compares(record)] == [True, True]
    ]
    assert both, result.records
    for record in both:
        a, b = record.args["a"], record.args["b"]
        assert a is b and isinstance(a, list) and above(a[0], 7)
    assert shared == [0]


# run-with-nested-arguments-walks-a-cycle-once, for bugs, so the run asks for every fork rather
# than stopping once every line and branch is covered
@pytest.mark.parametrize("isolation", WHERE)
def test_walks_a_cycle_once(isolation: Isolation) -> None:
    xs: list[object] = [0]
    xs.append(xs)
    target = load_target("targets.nested.holds_itself::check")

    result = run(target, {"xs": xs}, limits=Limits(goal=Goal.BUGS), isolation=isolation)

    assert result.stopped.kind is StopKind.NO_FORK
    lists = [record.args["xs"] for record in result.records]
    flipped = [each for each in lists if isinstance(each, list) and each and above(each[0], 5)]
    assert flipped, result.records
    assert all(len(solved) == 2 and solved[1] is solved for solved in flipped)


# run-with-nested-arguments-leaves-an-uncopyable-argument-plain
@pytest.mark.parametrize("isolation", WHERE)
def test_leaves_an_uncopyable_argument_plain(isolation: Isolation) -> None:
    box = objects.Box()

    result = run(load_target("targets.nested.objects::boxed"), {"box": box}, isolation=isolation)

    seeded = result.records[0]
    assert seeded.forks == () and seeded.downgrades == ()
    assert result.stopped.kind is StopKind.NO_FORK
    assert seeded.args["box"] is box
