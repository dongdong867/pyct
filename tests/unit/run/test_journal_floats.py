"""A float leaf crosses the journal as the same double, as the solver and the line need it."""

import math

import pytest

from pyct.core.branch import Branch, Site
from pyct.run.journal import JournalWriter, read
from pyct.run.run import run
from pyct.run.target import load_target

SITE = Site(file="t.py", line=2, col=7)

# doubles a float fork may hold: a plain one, both zeros, the smallest subnormal, the
# infinities and NaN
DOUBLES = [2.5, 0.0, -0.0, 5e-324, math.inf, -math.inf, math.nan]


@pytest.mark.parametrize("value", DOUBLES, ids=[repr(value) for value in DOUBLES])
def test_a_float_leaf_reads_back_as_the_same_double(value: float) -> None:
    buffer = bytearray(1 << 16)
    fork = Branch(expression=[">", ["+", "x", value], value], taken=False, site=SITE)

    JournalWriter(buffer).fork(fork)

    reading = read(buffer)
    assert reading.problem is None
    [branch] = reading.branches
    # repr tells -0.0 from 0.0 and reads NaN, where `==` does neither
    assert repr(branch.expression) == repr(fork.expression)
    assert (branch.taken, branch.site) == (fork.taken, fork.site)


def test_a_forked_input_hands_back_its_float_forks_and_a_nan_or_infinity_runs() -> None:
    target = load_target("targets.floats.nan_or_infinity::kind")

    result = run(target, {"x": 1.0})

    # each input ran in a child of its own, and its forks crossed back through the journal
    assert result.environment.isolated is True
    assert [record.failure for record in result.records] == [None, None, None]
    assert result.records[0].forks[1].expression == [">", "x", 1.7976931348623157e308]
    solved = sorted(repr(record.args["x"]) for record in result.records[1:])
    assert solved == ["inf", "nan"]
    assert all(record.mismatch_at is None for record in result.records[1:])
