"""execute keeps what the call reached beyond its lines: the functions it entered, with their
lines and branches, and the way each branch went."""

from collections.abc import Callable, Mapping

from pyct.core.branch import Branch, Fact, Site
from pyct.execution.execute import ExecutionContext, execute

SOURCE = """\
def helper(x):
    if x > 5:
        return 1
    return 0


def target(x):
    if x < 10:
        x = helper(x)
    return x


def other(x):
    if x:
        return 2
    return 3
"""


def loaded(name: str) -> Callable[..., object]:
    """A function of ``SOURCE``, compiled under a file name of its own."""
    namespace: dict[str, object] = {}
    exec(compile(SOURCE, "<reach>", "exec"), namespace)
    function = namespace[name]
    assert callable(function)
    return function


class Heard:
    """A watch that keeps the functions the call entered and the ways it went, in order, apart
    from the lines, forks, facts, downgrades and bounds it was told."""

    def __init__(self) -> None:
        self.reached: list[tuple[object, ...]] = []
        self.rest: list[object] = []

    def fork(self, branch: Branch) -> None:
        self.rest.append(branch)

    def fact(self, fact: Fact) -> None:
        self.rest.append(fact)

    def line(self, number: int) -> None:
        self.rest.append(number)

    def downgrade(self, name: str, site: Site, count: int) -> None:
        self.rest.append((name, site, count))

    def bound(self, note: str) -> None:
        self.rest.append(note)

    def entered(self, lines: frozenset[int], branches: Mapping[int, frozenset[int]]) -> None:
        self.reached.append(("entered", min(lines - {1, 7}), dict(branches)))

    def went(self, line: int, to: int) -> None:
        self.reached.append(("went", line, to))


def test_execute_keeps_the_functions_the_call_entered_and_the_ways_it_went() -> None:
    result = execute(ExecutionContext(fn=loaded("target"), file="<reach>"), {"x": 3})

    reach = result.reach
    assert {2, 3, 4, 8, 9, 10} <= reach.function_lines
    assert reach.function_lines.isdisjoint({14, 15, 16})
    assert reach.branches == {2: {3, 4}, 8: {9, 10}}
    assert reach.went == {(8, 9), (2, 4)}


def test_execute_keeps_no_function_the_call_did_not_enter() -> None:
    result = execute(ExecutionContext(fn=loaded("target"), file="<reach>"), {"x": 11})

    reach = result.reach
    assert {8, 9, 10} <= reach.function_lines
    assert reach.function_lines.isdisjoint({2, 3, 4})
    assert reach.branches == {8: {9, 10}}
    assert reach.went == {(8, 10)}


def test_execute_tells_the_watch_each_function_entered_and_each_way_once() -> None:
    heard = Heard()

    execute(ExecutionContext(fn=loaded("target"), file="<reach>"), {"x": 3}, watch=heard)
    execute(ExecutionContext(fn=loaded("target"), file="<reach>"), {"x": 3}, watch=heard)

    once = [
        ("entered", 8, {8: {9, 10}}),
        ("went", 8, 9),
        ("entered", 2, {2: {3, 4}}),
        ("went", 2, 4),
    ]
    assert heard.reached == once + once
