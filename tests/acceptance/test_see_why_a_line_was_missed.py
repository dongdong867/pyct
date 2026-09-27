"""Acceptance tests for the see-why-a-line-was-missed story.

Each test spawns ``python -P -m pyct`` through the harness and reads the
summary line's ``why_uncovered``, the seed's downgrade entries, or the
stderr trace, as a person or sweep would read them after a run.
"""

from tests.acceptance.harness import REPO_ROOT, first_line, one_line, run_pyct


def spec(module: str, function: str) -> tuple[str, str]:
    """A target under ``targets/why``: what the command line names, and F, its file."""
    return f"targets.why.{module}::{function}", str(REPO_ROOT / "targets" / "why" / f"{module}.py")


LOST, LOST_FILE = spec("lost", "lose")
SITES, SITES_FILE = spec("sites", "sites")


# see-why-a-line-was-missed-names-where-a-condition-was-lost
def test_names_where_a_condition_was_lost() -> None:
    result = run_pyct(LOST, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    assert seed["downgrades"] == [
        {"name": "__xor__", "count": 1, "file": LOST_FILE, "line": 2, "col": 8}
    ]
    assert f"downgrades __xor__ at {LOST_FILE}:2:8" in result.stderr.splitlines()


# see-why-a-line-was-missed-keeps-each-site-s-losses-apart
def test_keeps_each_site_s_losses_apart() -> None:
    result = run_pyct(SITES, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    assert first_line(result.stdout)["downgrades"] == [
        {"name": "__xor__", "count": 3, "file": SITES_FILE, "line": 3, "col": 12},
        {"name": "__xor__", "count": 1, "file": SITES_FILE, "line": 4, "col": 8},
    ]
    trace = result.stderr.splitlines()
    lost = f"downgrades __xor__ ×3 at {SITES_FILE}:3:12, __xor__ at {SITES_FILE}:4:8"
    assert lost in trace
