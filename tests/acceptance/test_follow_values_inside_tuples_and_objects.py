"""Acceptance tests for the follow-values-inside-tuples-and-objects child of the
run-with-nested-arguments story.

Each test calls ``run()``, since only a caller in Python can hand pyct a tuple, an object, or
one value under two names. A test about copies runs in a child process and in pyct's own,
where an input that changed the caller's value would show it to the next one.
"""

import json
import sys
from types import ModuleType
from typing import Any

import pytest

from pyct.config.goal import Goal
from pyct.config.limits import Limits
from pyct.results.record import InputRecord, StopKind
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.target import Target, load_target
from tests.acceptance.harness import let_pyct_run_in_process

# where an input runs, in a child process of its own or in the caller's
WHERE = [Isolation.FORK, Isolation.IN_PROCESS]
# and in a fresh interpreter, which takes the seed pickled
EVERYWHERE = [*WHERE, Isolation.FRESH]
OBJECTS = "targets.nested.objects"


def loaded(spec: str, monkeypatch: pytest.MonkeyPatch) -> tuple[Target, ModuleType]:
    """The target, and the module pyct loaded it from, whose classes a seed's objects are."""
    let_pyct_run_in_process(monkeypatch)
    target = load_target(spec)
    return target, sys.modules[target.fn.__module__]


def args_of(records: tuple[InputRecord, ...], name: str) -> list[Any]:
    """Each record's argument under ``name``, in order, as the object the target was handed."""
    return [record.args[name] for record in records]


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
def test_leaves_an_uncopyable_argument_plain(
    isolation: Isolation, monkeypatch: pytest.MonkeyPatch
) -> None:
    target, module = loaded(f"{OBJECTS}::boxed", monkeypatch)
    box = module.Box()

    result = run(target, {"box": box}, isolation=isolation)

    seeded = result.records[0]
    assert seeded.forks == () and seeded.downgrades == ()
    assert result.stopped.kind is StopKind.NO_FORK
    assert seeded.args["box"] is box


# run-with-nested-arguments-follows-an-object-s-attributes
@pytest.mark.parametrize("isolation", EVERYWHERE)
def test_follows_an_object_s_attributes(
    isolation: Isolation, monkeypatch: pytest.MonkeyPatch
) -> None:
    target, module = loaded(f"{OBJECTS}::classify_rule", monkeypatch)
    rule = module.Rule()

    result = run(target, {"rule": rule}, isolation=isolation)

    rules = args_of(result.records, "rule")
    assert all(type(each) is module.Rule and each.check is module.checked for each in rules)
    assert any(above(each.limit, 100) for each in rules), rules
    assert any(isinstance(each.limit, int) and each.limit < 0 for each in rules), rules
    assert any(each.label == "strict" for each in rules), rules
    limit = ["getattr", "rule", "'limit'"]
    assert result.records[0].forks[0].expression == [">", limit, 100]
    assert vars(rule) == {"limit": 10, "label": "x", "check": module.checked}


# run-with-nested-arguments-follows-an-instance-given-as-self
@pytest.mark.parametrize("isolation", WHERE)
def test_follows_an_instance_given_as_self(
    isolation: Isolation, monkeypatch: pytest.MonkeyPatch
) -> None:
    target, _ = loaded("targets.classes.shop::Cart.total", monkeypatch)
    assert target.self_class is not None
    given = target.self_class(owner="ann")

    result = run(target, {"self": given, "discount": 5}, isolation=isolation)

    owner = ["==", ["getattr", "self", "'owner'"], "'admin'"]
    instances = zip(args_of(result.records, "self"), result.records, strict=True)
    admins = [record for instance, record in instances if instance.owner == "admin"]
    assert admins, result.records
    assert all(any(fork.expression == owner for fork in record.forks) for record in admins)
    assert vars(given) == {"owner": "ann"}


# run-with-nested-arguments-keeps-an-alias-one-value, for an object
@pytest.mark.parametrize("isolation", WHERE)
def test_keeps_an_object_reached_by_two_paths_one_value(
    isolation: Isolation, monkeypatch: pytest.MonkeyPatch
) -> None:
    target, module = loaded(f"{OBJECTS}::two_counters", monkeypatch)
    shared = module.Counter()

    result = run(target, {"a": shared, "b": shared}, isolation=isolation)

    n = ["getattr", "a", "'n'"]
    named = {expression for record in result.records for expression, _ in compares(record)}
    assert named == {json.dumps([">", n, 5]), json.dumps([">", n, 7])}, named
    both = [
        record
        for record in result.records
        if [taken for _, taken in compares(record)] == [True, True]
    ]
    assert both, result.records
    for record in both:
        a, b = record.args["a"], record.args["b"]
        assert a is b and type(a) is module.Counter and above(a.n, 7)
    assert vars(shared) == {"n": 0}


# run-with-nested-arguments-walks-a-cycle-once, for an object
@pytest.mark.parametrize("isolation", WHERE)
def test_walks_an_object_that_holds_itself_once(
    isolation: Isolation, monkeypatch: pytest.MonkeyPatch
) -> None:
    target, module = loaded(f"{OBJECTS}::node_check", monkeypatch)
    node = module.Node()

    result = run(target, {"node": node}, limits=Limits(goal=Goal.BUGS), isolation=isolation)

    assert result.stopped.kind is StopKind.NO_FORK
    nodes = args_of(result.records, "node")
    assert all(each.me is each and each is not node for each in nodes)
    assert any(above(each.n, 5) for each in nodes), nodes
    assert node.n == 0


# a list and a dict inside an object are followed as an argument's are, each tracked whole
@pytest.mark.parametrize("isolation", WHERE)
def test_follows_a_list_and_a_dict_inside_an_object(
    isolation: Isolation, monkeypatch: pytest.MonkeyPatch
) -> None:
    target, module = loaded(f"{OBJECTS}::held", monkeypatch)

    result = run(target, {"holder": module.Holder()}, isolation=isolation)

    holders = args_of(result.records, "holder")
    assert all(type(each) is module.Holder for each in holders)
    assert any(each.items and above(each.items[0], 5) for each in holders), holders
    assert any(above(each.table.get("k"), 5) for each in holders), holders
    items = ["getattr", "holder", "'items'"]
    seeded = [fork.expression for fork in result.records[0].forks]
    assert [">", ["[]", items, 0], 5] in seeded, seeded
