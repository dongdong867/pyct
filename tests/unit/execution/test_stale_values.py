"""A tracked value an earlier call kept, used by a later call in the same process."""

from pathlib import Path

from pyct.execution.execute import ExecutionContext, execute
from pyct.results.record import DowngradeCount

KEEPS = Path(__file__).resolve().parents[3] / "targets" / "lists" / "keeps.py"


def test_a_value_an_earlier_call_kept_names_its_loss_on_the_later_call() -> None:
    namespace: dict[str, object] = {}
    exec(compile(KEEPS.read_text(), str(KEEPS), "exec"), namespace)
    ctx = ExecutionContext(fn=namespace["keep"], file=str(KEEPS))  # pyrefly: ignore[bad-argument-type]

    first = execute(ctx, {"items": [1]})
    later = execute(ctx, {"items": [9]})

    # the later call tests the first call's list, whose forks belong to a call that is over:
    # it records none of them, and names each condition it lost as a truth test
    assert first.downgrades == ()
    assert later.branches == ()
    assert later.downgrades == (DowngradeCount(name="__bool__", count=2),)
