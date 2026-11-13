"""A kept rewrite takes its condition's place only in a plan that holds it, on an input that holds
every name it reads, and only when it runs and records its own fork there."""

import types
from collections.abc import Mapping

from pyct.binding.bind import Seed
from pyct.branches.plan import plan
from pyct.core.foundation.branch import Branch, Site
from pyct.execution.execute import ExecutionResult
from pyct.results.causes import Condition
from pyct.rewrite.condition import rewrite_code
from pyct.rewrite.kept import Kept

SITE = Site("m.py", 2, 7)
CONDITION = Condition(SITE, True)
CODE = rewrite_code('s == "1e-30"', ("s",), "<rewrite m:2:7>")


def kept() -> Kept:
    found = Kept()
    assert isinstance(CODE, types.CodeType)
    found.keep(CONDITION, CODE, ("s",))
    return found


def never(code: types.CodeType, args: Mapping[str, object]) -> ExecutionResult | str:
    raise AssertionError("the rewrite does not run")


def test_a_plan_that_does_not_hold_the_condition_takes_no_rewrite() -> None:
    wanted = plan((Branch(["==", ["float", "s"], 1e-30], True, SITE),))
    assert wanted is not None

    assert kept().reused(wanted, Seed.of({"s": "0"}), never) is None


def test_an_input_without_a_name_the_rewrite_reads_takes_no_rewrite() -> None:
    wanted = plan((Branch(["==", ["float", "s"], 1e-30], False, SITE),))
    assert wanted is not None

    assert kept().reused(wanted, Seed.of({"t": "0"}), never) is None


def test_an_input_where_a_name_the_rewrite_reads_holds_an_object_takes_no_rewrite() -> None:
    wanted = plan((Branch(["==", ["float", "s"], 1e-30], False, SITE),))
    assert wanted is not None
    origin = Seed.of({"s": [{"__class__": "m::Order"}]})

    assert kept().reused(wanted, origin, never) is None


def test_a_rewrite_that_does_not_run_or_records_no_fork_takes_no_place() -> None:
    wanted = plan((Branch(["==", ["float", "s"], 1e-30], False, SITE),))
    assert wanted is not None
    origin = Seed.of({"s": "0"})

    assert kept().reused(wanted, origin, lambda *_: "cannot fork") is None
    assert kept().reused(wanted, origin, lambda *_: ExecutionResult(frozenset(), ())) is None
