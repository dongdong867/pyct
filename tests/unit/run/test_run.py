from pathlib import Path

from pyct.core.branch import Branch, Site
from pyct.results.failure import Failure, FailureKind
from pyct.run.run import run
from pyct.run.target import load_target

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = str(REPO_ROOT / "targets" / "trace" / "uncalled_helper.py")


def test_run_records_the_seed_and_measures_it_against_the_module() -> None:
    target = load_target("targets.trace.uncalled_helper::classify")

    result = run(target, {"x": 1})

    assert result.entry == "targets.trace.uncalled_helper::classify"
    assert len(result.records) == 1
    assert result.records[0].args == {"x": 1}
    assert result.records[0].covered_lines == frozenset({5, 6})
    assert result.coverage.covered == {FIXTURE: frozenset({5, 6})}
    assert result.coverage.total == {FIXTURE: 7}


def test_run_records_the_forks_the_seed_took() -> None:
    target = load_target("targets.trace.uncalled_helper::classify")

    result = run(target, {"x": 3})

    assert result.records[0].forks == (
        Branch(
            expression=["<", "x", 10],
            taken=True,
            site=Site(file=FIXTURE, line=5, col=7),
        ),
    )


def test_run_records_how_the_seed_ended() -> None:
    target = load_target("targets.trace.raises::explode")

    result = run(target, {"x": 3})

    assert result.records[0].failure == Failure(
        kind=FailureKind.TARGET_RAISED, detail="ValueError: too small"
    )
    assert result.records[0].covered_lines == frozenset({2, 3})
