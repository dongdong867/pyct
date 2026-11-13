"""execute hands back the recorded runs of the target's pieces when its code has the hooks, and
the call does what it does without them."""

import dataclasses
from collections.abc import Callable

import pytest

from pyct.core.foundation.branch import Changed, GoingIn, PieceRun, Site
from pyct.execution.execute import ExecutionContext, ExecutionResult, execute
from pyct.intercept.compiled import substituted_code
from tests.unit.intercept.loop_shapes import LOOPS

FILE = "<executed pieces>"


def call(source: str, args: dict[str, object], *, pieces: bool) -> ExecutionResult:
    """What one call of the source's `f` did, compiled with the switch as given."""
    namespace: dict[str, object] = {"g": lambda *_: None}
    exec(substituted_code(source.encode(), FILE, pieces=pieces), namespace)  # noqa: S102
    function = namespace["f"]
    assert isinstance(function, Callable)
    return execute(ExecutionContext(fn=function, file=FILE), args)


def test_execute_hands_back_each_recorded_run_with_a_tracked_argument_marked() -> None:
    result = call(LOOPS["while"], {"n": 2}, pieces=True)

    assert result.pieces == (
        PieceRun(
            site=Site(file=FILE, line=3, col=4),
            going_in=(GoingIn("i", "0", tracked=False), GoingIn("n", "2", tracked=True)),
            changed=(Changed("i", "2"),),
        ),
    )


# a shape, each with an argument that runs its loops
CALLS: dict[str, dict[str, object]] = {
    "while": {"n": 3},
    "for_else_break": {"xs": [1, 3]},
    "nested_break_in_else": {"xss": [[0, 1], [2]]},
    "while_and_or": {"s": "abz", "i": 0, "n": 3},
}


@pytest.mark.parametrize("shape", CALLS)
def test_the_call_does_with_the_hooks_what_it_does_without_them(shape: str) -> None:
    on = call(LOOPS[shape], CALLS[shape], pieces=True)
    off = call(LOOPS[shape], CALLS[shape], pieces=False)

    assert on.pieces
    assert off.pieces == ()
    assert dataclasses.replace(on, pieces=()) == off
