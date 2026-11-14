"""With the pieces switch on, each input's record holds the recorded runs of its pieces, the same
from a forked child, from pyct's own process and from a fresh interpreter, and the run is
otherwise the one it is with the switch off."""

import dataclasses
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from pyct.core.foundation.branch import Changed, GoingIn, PieceRun, Site
from pyct.intercept.hook import Interception, intercepting
from pyct.results.record import RunResult
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.target import load_target

LOOPED = """\
def f(n):
    t = 0
    for i in range(3):
        if n > i:
            t += 1
    w = [c for c in "ab" if n > 5]
    while t > 1:
        t -= 1
    if w:
        return t, w
    return t
"""


@pytest.fixture
def looped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A package of the target above, importable from the path, and its module file."""
    package = tmp_path / "looped_pieces"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "shapes.py").write_text(LOOPED)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield package / "shapes.py"
    forget_modules("looped_pieces")


def forget_modules(package: str) -> None:
    """Drop the package's modules, so the next run imports them again."""
    for name in [name for name in sys.modules if name.split(".")[0] == package]:
        del sys.modules[name]


def ran(
    spec: str, seed: Mapping[str, object], cache: Path, isolation: Isolation, *, pieces: bool
) -> RunResult:
    """The run of the spec from the seed, its package intercepted with the switch as given."""
    module = spec.partition("::")[0]
    with intercepting(Interception(module=module, cache=cache, pieces=pieces)):
        return run(load_target(spec), seed, setup=Setup(isolation=isolation))


@pytest.mark.parametrize("isolation", [Isolation.FORK, Isolation.IN_PROCESS, Isolation.FRESH])
def test_each_input_records_its_pieces_runs_however_it_runs(
    looped: Path, tmp_path: Path, isolation: Isolation
) -> None:
    result = ran("looped_pieces.shapes::f", {"n": 2}, tmp_path / "cache", isolation, pieces=True)

    def site(line: int, col: int) -> Site:
        return Site(file=str(looped), line=line, col=col)

    n = GoingIn("n", "2", tracked=True)
    assert result.records[0].pieces == (
        PieceRun(site(3, 4), (n, GoingIn("t", "0", tracked=False)), (Changed("t", "2"),)),
        PieceRun(site(6, 8), (n,), (Changed("w", "[]"),)),
        PieceRun(site(7, 4), (GoingIn("t", "2", tracked=False),), (Changed("t", "1"),)),
    )
    # every input the solver gave records the same three pieces, each with its own values
    assert len(result.records) > 1
    assert all(len(record.pieces) == 3 for record in result.records)


def test_a_forked_child_pyct_s_process_and_a_fresh_interpreter_record_the_same_runs(
    looped: Path, tmp_path: Path
) -> None:
    def pieces_of(isolation: Isolation) -> list[object]:
        forget_modules("looped_pieces")
        result = ran(
            "looped_pieces.shapes::f", {"n": 2}, tmp_path / "cache", isolation, pieces=True
        )
        return [(record.args, record.pieces) for record in result.records]

    forked = pieces_of(Isolation.FORK)

    assert pieces_of(Isolation.IN_PROCESS) == forked
    assert pieces_of(Isolation.FRESH) == forked


# targets that hold loops and comprehensions, each with a seed, whose runs cover every line and
# branch and stop
WITH_LOOPS = [
    ("targets.dicts.walk_keys::counted", {"d": {"a": 1, "b": 2}}),
    ("targets.lists.loop_passes::count", {"items": [0, 20]}),
    ("targets.stop.comprehension::pick", {"s": "ab"}),
    ("targets.stop.count_x::count", {"s": "xx"}),
    ("targets.strs.digit_checksum::checksum", {"number": "41111111"}),
]


@pytest.mark.parametrize(("spec", "seed"), WITH_LOOPS, ids=[spec for spec, _ in WITH_LOOPS])
def test_with_the_switch_on_a_run_is_the_one_it_is_off_but_for_the_recorded_runs(
    spec: str, seed: Mapping[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    off = ran(spec, seed, tmp_path / "off", Isolation.IN_PROCESS, pieces=False)
    for name in [name for name in sys.modules if name.split(".")[0] == "targets"]:
        monkeypatch.delitem(sys.modules, name)
    on = ran(spec, seed, tmp_path / "on", Isolation.IN_PROCESS, pieces=True)

    assert any(record.pieces for record in on.records)
    assert [dataclasses.replace(record, pieces=()) for record in on.records] == list(off.records)
    assert (on.coverage, on.stopped, on.misses) == (off.coverage, off.stopped, off.misses)
