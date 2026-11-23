"""A loop in use inside a real input, in a forked child that inherits the loops in use: a formula
that matches gives the input a tracked value after the loop and no fork inside it, and one that
does not leaves the input's record carrying the drop."""

from collections.abc import Callable, Iterator, Mapping
from pathlib import Path

import pytest

from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.core.entry import in_use
from pyct.core.entry.in_use import LoopInUse
from pyct.core.foundation.branch import DropReason, FormulaDrop, Site
from pyct.intercept.hook import Interception, intercepting
from pyct.results.record import RunResult
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.target import load_target
from tests.unit.run.test_run_pieces import forget_modules

COUNTS = """\
def f(s):
    t = 0
    for c in s:
        if c == "z":
            t += 1
    if t > 1:
        return 1
    return 0
"""
LOOP, AFTER = (3, 4), 6


@pytest.fixture
def counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A package of the target above, importable from the path, and its module file."""
    package = tmp_path / "in_use_loops"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "counts.py").write_text(COUNTS)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield package / "counts.py"
    forget_modules("in_use_loops")


def ran(
    file: Path,
    formula: Callable[[Mapping[str, object]], Mapping[str, object]],
    seed: Mapping[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> RunResult:
    """The run of the target from the seed, its loop in use with the formula, each input in a
    forked child."""
    monkeypatch.setitem(in_use.IN_USE, (str(file), *LOOP), LoopInUse(("s", "t"), ("t",), formula))
    interception = Interception(module="in_use_loops.counts", cache=tmp_path / "cache", pieces=True)
    with intercepting(interception):
        return run(
            load_target("in_use_loops.counts::f"),
            seed,
            limits=Limits(budget=Budget(seconds=60)),
            setup=Setup(isolation=Isolation.FORK),
        )


def counted(by: str) -> Callable[[Mapping[str, object]], Mapping[str, object]]:
    """The loop's formula, counting ``by`` in the str."""

    def formula(values: Mapping[str, object]) -> Mapping[str, object]:
        s, t = values["s"], values["t"]
        assert isinstance(s, str)
        assert isinstance(t, int)
        return {"t": t + s.count(by)}

    return formula


def test_a_formula_that_matches_leaves_only_the_tracked_fork_after_the_loop(
    counts: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = ran(counts, counted("z"), {"s": "az"}, tmp_path, monkeypatch)

    condition = [">", ["+", 0, ["count", "s", "'z'"]], 1]
    assert [record.failure for record in result.records] == [None, None]
    assert [[(f.expression, f.site.line, f.taken) for f in r.forks] for r in result.records] == [
        [(condition, AFTER, False)],
        [(condition, AFTER, True)],
    ]
    assert all(record.drops == () for record in result.records)


def test_a_formula_that_does_not_match_leaves_its_drop_on_the_input_s_record(
    counts: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = ran(counts, counted("a"), {"s": "zz"}, tmp_path, monkeypatch)

    site = Site(str(counts), *LOOP)
    drop = FormulaDrop(site, "t", "2", "0", DropReason.MISMATCH, run=0)
    assert result.records[0].drops == (drop,)
    # the loop ran plain before the drop, and its value stays plain after it
    assert result.records[0].forks == ()
