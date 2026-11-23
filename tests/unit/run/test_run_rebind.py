"""A hook rebinds its caller's names inside a real input, under pyct's coverage and the deadline's
alarm, the same in a forked child, in pyct's own process and in a fresh interpreter: a tracked
value rebound to a plain one records no fork, and rebound back records one again."""

from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.intercept.hook import Interception, intercepting
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.target import load_target
from tests.unit.run.test_run_pieces import forget_modules

REBOUND = """\
import sys

from pyct.core.entry.frames import rebind


def swap(**values):
    rebind(sys._getframe(1), values)


def f(n):
    kept = n
    swap(n=7)
    if n > 5:
        a = 1
    else:
        a = 2
    swap(n=kept)
    if n > 3:
        return a
    return -a
"""
# the lines of the target above: the condition on the plain value, its two sides, and the
# condition on the tracked value again
PLAIN_IF, PLAIN_YES, PLAIN_NO, TRACKED_IF = 13, 14, 16, 18


@pytest.fixture
def rebound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A package of the target above, importable from the path, and its module file."""
    package = tmp_path / "rebound_names"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "swaps.py").write_text(REBOUND)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield package / "swaps.py"
    forget_modules("rebound_names")


@pytest.mark.parametrize("isolation", [Isolation.FORK, Isolation.IN_PROCESS, Isolation.FRESH])
def test_a_hook_rebinds_its_caller_s_names_inside_an_input_however_it_runs(
    rebound: Path, tmp_path: Path, isolation: Isolation
) -> None:
    interception = Interception(module="rebound_names.swaps", cache=tmp_path / "cache")
    with intercepting(interception):
        result = run(
            load_target("rebound_names.swaps::f"),
            {"n": 2},
            limits=Limits(budget=Budget(seconds=60)),
            setup=Setup(isolation=isolation),
        )

    assert [record.failure for record in result.records] == [None, None]
    seed, solved = result.records
    # the plain 7 records no fork and takes the yes side for every n; the tracked n records
    # its fork again, and the solver's input takes the other side of it
    assert [(fork.site.line, fork.taken) for fork in seed.forks] == [(TRACKED_IF, False)]
    assert [(fork.site.line, fork.taken) for fork in solved.forks] == [(TRACKED_IF, True)]
    assert seed.args == {"n": 2}
    assert cast(int, solved.args["n"]) > 3
    for record in result.records:
        assert {PLAIN_IF, PLAIN_YES, TRACKED_IF} <= record.covered_lines
        assert PLAIN_NO not in record.covered_lines
