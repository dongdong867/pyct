"""Acceptance tests for the bound-an-int-read-from-a-string-by-its-length ticket.

Each test spawns ``python -P -m pyct`` through the harness with the real cvc5. Under
`s.isdigit()` and `len(s) <= 5`, `int(s)` can never be 100000 or 200000, but cvc5 took seconds
to see it, and the gate's budget ran out on those forks before the shallow ones were asked.
"""

import pytest

from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct

INT_NOT_IN = "targets.why.negated::int_not_in"
NEGATED_FILE = str(REPO_ROOT / "targets" / "why" / "negated.py")
# the `return 0` a string of other characters reaches, and the one a string of six digits does
SHALLOW_RETURNS = {83, 85}


def covered_in(stdout: str, file: str) -> set[int]:
    """The lines of one file any input ran."""
    lines: set[int] = set()
    for line in input_lines(stdout):
        covered = line["covered"]
        assert isinstance(covered, dict), line
        lines |= {int(number) for number in covered.get(file, [])}
    return lines


@pytest.mark.serial
def test_reaches_the_shallow_forks_within_the_gate_s_budget() -> None:
    result = run_pyct(INT_NOT_IN, '{"s": "7"}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    assert covered_in(result.stdout, NEGATED_FILE) >= SHALLOW_RETURNS, result.stdout
