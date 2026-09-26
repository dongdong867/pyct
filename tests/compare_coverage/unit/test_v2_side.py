"""The v2 side: ``pyct run`` in a process of its own, read by its summary line."""

import json
import os
import sys
from pathlib import Path

from tools.compare_coverage.process import side_environment
from tools.compare_coverage.sides import Limits, SideReport, SideRequest
from tools.compare_coverage.v2_side import Stamp, V2Side

REPO_ROOT = Path(__file__).resolve().parents[3]
ONE_CHECK = str(REPO_ROOT / "targets" / "flip" / "one_check.py")
HERE = Stamp.here()

# stands in for pyct: prints its argv to stderr and the summary line it is given in FAKE_SUMMARY
FAKE_PYCT = """\
import os, sys
print(" ".join(sys.argv[1:]), file=sys.stderr)
print(os.environ["FAKE_SUMMARY"])
"""


def request(budget: float = 30.0) -> SideRequest:
    target = "targets.flip.one_check::classify"
    limits = Limits(budget=budget)
    return SideRequest(target=target, seed={"x": 0}, root=REPO_ROOT, limits=limits, wait=60)


def fake_side(tmp_path: Path, summary: dict[str, object]) -> V2Side:
    script = tmp_path / "fake_pyct.py"
    script.write_text(FAKE_PYCT)
    environment = {**side_environment(os.environ), "FAKE_SUMMARY": json.dumps(summary)}
    return V2Side(program=(sys.executable, str(script)), environment=environment, stamp=HERE)


def summary(**fields: object) -> dict[str, object]:
    line: dict[str, object] = {
        "stopped": "no fork to flip",
        "inputs": 2,
        "covered": {"/t.py": [2, 3]},
        "environment": {"python": HERE.python, "cvc5": "1.3.4", "platform": HERE.platform},
    }
    return {**line, **fields}


def test_the_side_runs_pyct_run_and_reads_its_summary_line() -> None:
    program = (sys.executable, "-P", "-m", "pyct")
    side = V2Side(program=program, environment=side_environment(os.environ), stamp=HERE)

    report = side.run(request(budget=10.0))

    assert report == SideReport(
        file=ONE_CHECK, covered=frozenset({2, 3, 4}), stopped="no fork to flip", inputs=2
    )


def test_the_limits_are_given_as_pyct_runs_flags(tmp_path: Path) -> None:
    side = fake_side(tmp_path, summary())

    assert side.given(Limits(5.0, 3, 2.5)) == {"budget": 5.0, "plateau": 3, "solver_timeout": 2.5}


def test_a_summary_line_that_names_another_python_fails_naming_both(tmp_path: Path) -> None:
    other = {"python": "3.99.0", "cvc5": "1.3.4", "platform": "Other-1.0"}
    side = fake_side(tmp_path, summary(environment=other))

    report = side.run(request())

    assert report.failure == (
        f"ran in Python 3.99.0 on Other-1.0, the checker in Python {HERE.python} on {HERE.platform}"
    )
    assert report.covered == frozenset({2, 3})


def test_a_summary_line_with_no_environment_fails(tmp_path: Path) -> None:
    line = summary()
    del line["environment"]

    report = fake_side(tmp_path, line).run(request())

    assert report.failure == "the summary line has no environment"


def test_a_summary_line_that_names_two_files_is_unreadable(tmp_path: Path) -> None:
    side = fake_side(tmp_path, summary(covered={"/a.py": [1], "/b.py": [2]}))

    report = side.run(request())

    assert report.failure is not None
    assert "covered must name the one file" in report.failure
