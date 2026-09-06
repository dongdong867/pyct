import sys
from pathlib import Path

import pytest

from pyct.run.run import run
from pyct.run.target import load_target

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = str(REPO_ROOT / "targets" / "trace" / "uncalled_helper.py")


@pytest.fixture(autouse=True)
def _forget_fixture_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    for name in [n for n in sys.modules if n.startswith("targets.")]:
        monkeypatch.delitem(sys.modules, name)


def test_run_records_the_seed_and_measures_it_against_the_module() -> None:
    target = load_target("targets.trace.uncalled_helper::classify")

    result = run(target, {"x": 1})

    assert result.entry == "targets.trace.uncalled_helper::classify"
    assert len(result.records) == 1
    assert result.records[0].args == {"x": 1}
    assert result.records[0].new_lines == frozenset({5, 6})
    assert result.coverage.covered == {FIXTURE: frozenset({5, 6})}
    assert result.coverage.total == {FIXTURE: 7}
