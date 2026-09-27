"""A tracked value an earlier call kept, used by a later call in the same process."""

from pathlib import Path

from pyct.core.branch import Site
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
    # it records none of them, and names each condition it lost by what lost it: the index's
    # check, then the truth test
    assert first.downgrades == ()
    assert later.branches == ()
    # both at the target's `if _KEPT[0][0] > 5:`, where the lost forks were taken
    at = Site(file=str(KEEPS), line=7, col=7)
    assert later.downgrades == (
        DowngradeCount(name="__getitem__", count=1, site=at),
        DowngradeCount(name="__bool__", count=1, site=at),
    )


def test_a_lost_fork_is_named_by_the_operation_that_lost_it() -> None:
    kept: list[object] = []

    def keep(items: list[int]) -> None:
        kept.append(items)
        first = kept[0]
        assert isinstance(first, list)
        for _ in first:
            pass
        if first:
            pass

    ctx = ExecutionContext(fn=keep, file=__file__)
    execute(ctx, {"items": [1]})
    later = execute(ctx, {"items": [2]})

    # the walk's step and the index's check are lost in `__iter__` and `__getitem__`, the
    # truth test in `__bool__`
    assert [entry.name for entry in later.downgrades] == ["__iter__", "__bool__"]
