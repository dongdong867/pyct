"""Acceptance tests for read-an-is-test-against-a-name-per-pass.

An `is` test that records a fork of its own, against a name bound to False,
a parenthesized False or in a loop beside a plain pass, names its own site
as the cause, in the side its operand needed, on every release.
"""

from tests.acceptance.harness import run_pyct
from tests.acceptance.test_see_why_a_line_was_missed_paths import (
    cause,
    entry_for,
    not_taken,
    spec,
)


def _why_line(stderr: str, line: int) -> str:
    """The one stderr `why` line for ``line``."""
    found = [each for each in stderr.splitlines() if each.startswith(f"why {line} in ")]
    assert len(found) == 1, stderr
    return found[0]


# read-an-is-test-against-a-name-per-pass-names-a-test-against-a-false-name
def test_a_test_against_a_false_name_names_its_own_site() -> None:
    target, file = spec("named", "false_flag")

    result = run_pyct(target, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    assert cause(entry_for(result.stdout, 9)) == not_taken(file, 8, 7, False, unsat=1)
    assert _why_line(result.stderr, 9) == f"why 9 in {file}: {file}:8:7 never false: 1 unsat"


# read-an-is-test-against-a-name-per-pass-names-a-test-against-a-parenthesized-constant
def test_a_test_against_a_parenthesized_false_names_its_own_site() -> None:
    target, file = spec("named", "parenthesized_false")

    result = run_pyct(target, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    assert cause(entry_for(result.stdout, 18)) == not_taken(file, 17, 7, False, unsat=1)


# read-an-is-test-against-a-name-per-pass-names-an-is-not-against-a-false-name
def test_an_is_not_against_a_false_name_names_its_own_site() -> None:
    target, file = spec("named", "is_not_false_flag")

    result = run_pyct(target, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    assert cause(entry_for(result.stdout, 27)) == not_taken(file, 26, 7, True, unsat=1)


# read-an-is-test-against-a-name-per-pass-keeps-a-mixed-loop-s-cause
def test_a_loop_of_a_tracked_and_a_plain_pass_keeps_its_cause() -> None:
    target, file = spec("named", "mixed_loop")

    result = run_pyct(target, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    assert cause(entry_for(result.stdout, 37)) == not_taken(file, 36, 11, False, unsat=1)


# read-an-is-test-against-a-name-per-pass-reads-a-chain-link-without-a-fork-in-the-is-sense
def test_a_chain_s_is_link_with_no_fork_reads_in_the_is_sense() -> None:
    target, file = spec("named", "chain_link")

    result = run_pyct(target, '{"x": 0, "b": true}')

    assert result.returncode == 0, result.stderr
    condition = entry_for(result.stdout, 45)["condition"]
    assert condition == {"file": file, "line": 44, "col": 7, "side": True}


# a chain's two `is` links share one site and both fork there: each reads as on the base
def test_a_chain_of_two_forking_is_links_reads_as_before() -> None:
    target, file = spec("named", "two_is_links")

    result = run_pyct(target, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    assert cause(entry_for(result.stdout, 56)) == not_taken(file, 55, 7, False, unsat=2)


# a chain whose one `is` link forks: its forks are its own, and the body needs b false
def test_a_chain_s_one_forking_is_link_reads_per_fork() -> None:
    target, file = spec("named", "compare_then_is")

    result = run_pyct(target, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    assert cause(entry_for(result.stdout, 66)) == not_taken(file, 65, 7, False, unsat=2)
