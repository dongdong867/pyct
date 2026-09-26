"""Acceptance tests for compare-coverage-on-the-fixtures: a side that fails fails its row.

v2 is the real ``pyct run`` and legacy the stub engine, so each failure is exact. Most go
through ``compare()``, as pyct's own tests go through ``run()``, because they need an entry
the committed list does not hold, a side aimed at a fake, or a one-second grace.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from tests.compare_coverage.acceptance.checker import (
    IMPLIED_CHECK,
    ONE_CHECK,
    ONE_CHECK_ENTRY,
    REPO_ROOT,
    a_run,
    compare_on,
    legacy_side,
    one_row,
    roots,
    run_checker,
    v2_side,
)
from tests.compare_coverage.conftest import StubCheckout
from tools.compare_coverage.compare import Sides
from tools.compare_coverage.entries import Entry
from tools.compare_coverage.sides import Limits
from tools.compare_coverage.v2_side import Stamp

IMPLIED_ENTRY = Entry(set="v2", module="targets.flip.implied_check", name="narrow", seed={"x": 3})

# stands in for pyct run: a summary line stamped with a Python that is not the checker's
OTHER_PYTHON = """\
import json
print(json.dumps({
    "stopped": "no fork to flip",
    "inputs": 1,
    "covered": {%r: [2, 3]},
    "environment": {"python": "3.99.0", "cvc5": "1.3.4", "platform": "Other-1.0"},
}))
"""


def real_sides(stub: StubCheckout) -> Sides:
    return Sides(v2=v2_side(), legacy=legacy_side(stub.path))


def test_fails_a_target_v2_refuses(stub_checkout: StubCheckout) -> None:
    """compare-coverage-against-legacy-fails-a-target-v2-refuses"""
    refused = Entry(
        set="v2", module="targets.annotations.plain", name="echo_number", seed={"n": "5"}
    )
    run = a_run([refused, ONE_CHECK_ENTRY], roots(stub_checkout.path))

    code, (row, after), _ = compare_on(run, real_sides(stub_checkout))

    assert row["status"] == "v2 failed"
    assert row["v2"]["failure"] == 'exit 2: n must be an int, got "5"'
    assert row["legacy"]["failure"] is None
    assert after["target"] == ONE_CHECK
    assert code == 1


def test_fails_a_target_legacy_cannot_run(stub_checkout: StubCheckout) -> None:
    """compare-coverage-against-legacy-fails-a-target-legacy-cannot-run"""
    error = {"success": False, "stopped": "error", "error": "cannot inspect target: boom"}
    stub_checkout.script({ONE_CHECK: error})

    result = run_checker("--legacy", str(stub_checkout.path), "--target", ONE_CHECK)

    row = one_row(result.stdout, result.stderr)
    assert row["status"] == "legacy failed"
    assert row["legacy"]["failure"] == "error: cannot inspect target: boom"
    assert "cannot inspect target: boom" in result.stderr
    assert result.returncode == 1


def test_fails_a_quiet_success(stub_checkout: StubCheckout, tmp_path: Path) -> None:
    """compare-coverage-against-legacy-fails-a-quiet-success"""
    stub_checkout.script({ONE_CHECK: {"exit": 0}})

    code, (silent,), _ = compare_on(
        a_run([ONE_CHECK_ENTRY], roots(stub_checkout.path)), real_sides(stub_checkout)
    )

    assert silent["status"] == "legacy failed"
    assert silent["legacy"]["failure"] == "no summary line"
    assert code == 1

    fake = tmp_path / "fake_pyct.py"
    fake.write_text(OTHER_PYTHON % str(REPO_ROOT / "targets" / "flip" / "one_check.py"))
    sides = Sides(v2=v2_side((sys.executable, str(fake))), legacy=legacy_side(stub_checkout.path))
    stub_checkout.script({})

    code, (stamped,), _ = compare_on(a_run([ONE_CHECK_ENTRY], roots(stub_checkout.path)), sides)

    here = Stamp.here()
    assert stamped["status"] == "v2 failed"
    assert stamped["v2"]["failure"] == (
        f"ran in Python 3.99.0 on Other-1.0, the checker in Python {here.python} on {here.platform}"
    )
    assert code == 1


def test_stops_a_side_that_runs_too_long(stub_checkout: StubCheckout) -> None:
    """compare-coverage-against-legacy-stops-a-side-that-runs-too-long"""
    stub_checkout.script({ONE_CHECK: {"sleep": 30}})
    run = a_run(
        [ONE_CHECK_ENTRY, IMPLIED_ENTRY], roots(stub_checkout.path), limits=Limits(budget=1.0)
    )

    code, (stopped, after), stderr = compare_on(run, real_sides(stub_checkout))

    # the budget is 1 s and the grace 1 s, so the side is stopped after 2 s
    assert stopped["status"] == "legacy failed"
    assert stopped["legacy"]["failure"] == "stopped after 2 s"
    assert after["target"] == IMPLIED_CHECK
    assert "stopped after 2 s" in stderr
    assert code == 1


def test_v2s_pyct_loads_shutil_before_any_target() -> None:
    # the next test's one-side case rests on this: if it fails, that test needs a module
    # pyct loads at startup and the adapter does not
    loaded = subprocess.run(
        [sys.executable, "-P", "-c", "import sys, pyct.cli; print('shutil' in sys.modules)"],
        capture_output=True,
        text=True,
        check=True,
    )

    assert loaded.stdout.strip() == "True"


def test_fails_a_side_that_loads_another_file(stub_checkout: StubCheckout, tmp_path: Path) -> None:
    """compare-coverage-against-legacy-fails-a-side-that-loads-another-file"""
    # v2's pyct has loaded the standard library's shutil before any target, so its side
    # takes that one; the adapter has not, so the legacy side loads the file the entry names
    (tmp_path / "shutil.py").write_text("def which(cmd: str) -> str:\n    return cmd\n")
    (tmp_path / "alias.py").write_text("def real(x: int) -> int:\n    return x\n\n\nnamed = real\n")
    entries = [
        Entry(set="v2", module="shutil", name="which", seed={"cmd": "x"}),
        Entry(set="v2", module="alias", name="named", seed={"x": 0}),
    ]
    run = a_run(entries, roots(stub_checkout.path, v2=tmp_path))

    code, (shadowed, alias), _ = compare_on(run, real_sides(stub_checkout))

    named = str(tmp_path / "shutil.py")
    assert shadowed["status"] == "v2 failed"
    assert shadowed["v2"]["file"] == shutil.__file__
    assert shadowed["v2"]["failure"] == f"loaded {shutil.__file__}, the entry names {named}"
    assert shadowed["legacy"]["failure"] is None
    no_def = f"{tmp_path / 'alias.py'} has no top-level def or class named named"
    assert alias["status"] == "both failed"
    assert alias["v2"]["failure"] == alias["legacy"]["failure"] == no_def
    assert code == 1
