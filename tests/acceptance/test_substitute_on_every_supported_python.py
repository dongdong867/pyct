"""Acceptance tests for substitute-on-every-supported-python: interception on each release.

Each test runs pyct on the Python that runs the suite, so a criterion "on each release"
holds when the suite passes on 3.12, 3.13 and 3.14. The lines-up criterion is
`tests.unit.intercept.test_lines_up`, over its corpus on the release it runs on.
"""

import os
import subprocess
import sys

from tests.acceptance.harness import (
    REPO_ROOT,
    argument,
    first_line,
    forks_of,
    input_lines,
    run_pyct,
    summary_line,
)
from tests.acceptance.test_bools import failure_of, sides
from tests.acceptance.test_return_a_real_bool_from_a_bool_method import sited
from tests.acceptance.test_strs import text
from tests.acceptance.test_substitute_is_and_in import compiled_total, covered_of, plain_lines

INTERCEPT = REPO_ROOT / "targets" / "intercept"
RELEASES = "targets.intercept.releases"
SPREAD_OPERAND_FILE = INTERCEPT / "spread_operand.py"
WARNING = "pyct intercepts builtins"


# substitute-on-every-supported-python-records-is-true-and-in-on-each-release
def test_records_is_true_and_in_on_each_release() -> None:
    result = run_pyct(f"{RELEASES}::f", '{"x": 0, "s": "zz"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    seed = inputs[0]
    assert sited(seed) == [
        (2, 7, [">", "x", 0], False),
        (4, 7, ["in", "s", "'abc'"], False),
    ]
    assert seed["downgrades"] == []
    assert sides(inputs, [">", "x", 0]) == {True, False}
    assert sides(inputs, ["in", "s", "'abc'"]) == {True, False}
    # each side a solver line took is the one plain Python takes on its arguments
    for line in inputs[1:]:
        assert sides([line], [">", "x", 0]) == {argument(line, "x") > 0}, line
        assert sides([line], ["in", "s", "'abc'"]) <= {text(line, "s") in "abc"}, line
    assert not [line for line in result.stderr.splitlines() if line.startswith(WARNING)]


# substitute-on-every-supported-python-follows-a-conversion-on-each-release
def test_follows_a_conversion_on_each_release() -> None:
    result = run_pyct(f"{RELEASES}::g", '{"s": "7"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert sited(inputs[0]) == [(10, 11, ["isint", "s"], True)]
    assert inputs[0]["downgrades"] == []
    assert sides(inputs[1:], ["isint", "s"]) == {False}


# substitute-on-every-supported-python-binds-len-on-each-release
def test_binds_len_on_each_release() -> None:
    result = run_pyct(f"{RELEASES}::sized", '{"s": "a"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert [(fork["expression"], fork["taken"]) for fork in forks_of(inputs[0])] == [
        (["==", ["len", "s"], 3], False)
    ]
    assert inputs[0]["downgrades"] == []
    assert any(len(text(line, "s")) == 3 for line in inputs[1:]), inputs


# substitute-on-every-supported-python-covers-a-spread-operand-as-written
def test_covers_a_spread_operand_as_written() -> None:
    result = run_pyct("targets.intercept.spread_operand::h", '{"s": "zz"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    expression = ["in", ["strip", "s"], "'abc'"]
    assert sited(inputs[0]) == [(5, 7, expression, False)]
    assert sides(inputs[1:], expression) == {True}
    for line in inputs:
        assert covered_of(line, SPREAD_OPERAND_FILE) == plain_lines(
            SPREAD_OPERAND_FILE, "h", text(line, "s")
        )
    total = summary_line(result.stdout)["total"]
    assert total == {str(SPREAD_OPERAND_FILE): compiled_total(SPREAD_OPERAND_FILE)}


# the command, on a Python release the hook reads as 3.99, which no suite has checked
_UNCHECKED_RELEASE = """\
import sys, types
from pyct.intercept import hook
hook.sys = types.SimpleNamespace(version_info=(3, 99, 0, "final", 0), meta_path=sys.meta_path)
from pyct.cli import entry
sys.exit(entry())
"""


def run_on_an_unchecked_release(*argv: str) -> subprocess.CompletedProcess[str]:
    """``pyct run`` as `run_pyct` spawns it, on a release outside the checked ones."""
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    return subprocess.run(
        [sys.executable, "-P", "-c", _UNCHECKED_RELEASE, "run", *argv],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


# substitute-on-every-supported-python-names-the-checked-releases-elsewhere
def test_names_the_checked_releases_elsewhere() -> None:
    result = run_on_an_unchecked_release(f"{RELEASES}::f", '--args={"x": 0, "s": "zz"}')

    assert result.returncode == 0, result.stderr
    warning = (
        "pyct intercepts builtins and the operations it substitutes on Python 3.12, 3.13, 3.14"
        " only; on 3.99 the target runs as written"
    )
    assert result.stderr.splitlines().count(warning) == 1, result.stderr
    assert WARNING not in result.stdout
    assert [fork for fork in forks_of(first_line(result.stdout)) if fork["line"] in (2, 4)] == []


# substitute-on-every-supported-python-leaves-a-conversion-raise-to-the-target
def test_leaves_a_conversion_raise_to_the_target() -> None:
    result = run_pyct(f"{RELEASES}::g", '{"s": "7"}')

    assert result.returncode == 0, result.stderr
    refused = [
        line for line in input_lines(result.stdout) if sides([line], ["isint", "s"]) == {False}
    ]
    assert refused, result.stdout
    for line in refused:
        s = text(line, "s")
        failure = failure_of(line)
        assert failure["kind"] == "target_raised", line
        assert failure["detail"] == f"ValueError: {_int_refusal(s)}"


def _int_refusal(s: str) -> str:
    """What plain Python says when `int` refuses the text, on the release running the suite."""
    try:
        int(s)
    except ValueError as error:
        return str(error)
    raise AssertionError(f"int takes {s!r}")
