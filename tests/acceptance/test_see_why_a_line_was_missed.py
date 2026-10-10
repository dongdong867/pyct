"""Acceptance tests for the see-why-a-line-was-missed story.

Each test spawns ``python -P -m pyct`` through the harness and reads the
summary line's ``why_uncovered``, the seed's downgrade entries, or the
stderr trace, as a person or sweep would read them after a run.
"""

import shutil
from pathlib import Path

from tests.acceptance.harness import (
    REPO_ROOT,
    first_line,
    input_lines,
    one_line,
    run_pyct,
    summary_line,
)


def spec(module: str, function: str) -> tuple[str, str]:
    """A target under ``targets/why``: what the command line names, and F, its file."""
    return f"targets.why.{module}::{function}", str(REPO_ROOT / "targets" / "why" / f"{module}.py")


UNTAKEN, UNTAKEN_FILE = spec("untaken", "same")
NOT_TRIED, NOT_TRIED_FILE = spec("not_tried", "two")
UNCALLED, UNCALLED_FILE = spec("uncalled", "f")
LOST, LOST_FILE = spec("lost", "lose")
LEFT, LEFT_FILE = spec("left", "left")
PLAIN, PLAIN_FILE = spec("plain", "big")
NESTED, NESTED_FILE = spec("nested", "deep")
EARLY, EARLY_FILE = spec("early", "early")
DIVIDES, DIVIDES_FILE = spec("divides", "divide")
HANDLER, HANDLER_FILE = spec("handler", "parse")
ENDS, ENDS_FILE = spec("ends", "ends")
SITES, SITES_FILE = spec("sites", "sites")
TWO_GUARDS, TWO_GUARDS_FILE = spec("two_guards", "two")

NO_TRIES = {
    "not_tried": 0,
    "unsat": 0,
    "unknown": 0,
    "timeout": 0,
    "left_the_plan": 0,
    "decided": 0,
}


def why_uncovered(stdout: str) -> list[dict[str, object]]:
    """The summary line's causes, one entry per cause."""
    entries = summary_line(stdout)["why_uncovered"]
    assert isinstance(entries, list), stdout
    return entries


def entry_for(stdout: str, line: int) -> dict[str, object]:
    """The one cause whose lines hold ``line``."""
    holding = [entry for entry in why_uncovered(stdout) if line in entry["lines"]]  # type: ignore[operator]
    assert len(holding) == 1, why_uncovered(stdout)
    return holding[0]


def condition(file: str, line: int, col: int, side: bool) -> dict[str, object]:
    return {"file": file, "line": line, "col": col, "side": side}


# see-why-a-line-was-missed-names-the-side-no-input-took
def test_names_the_side_no_input_took() -> None:
    result = run_pyct(UNTAKEN, '{"x": 2}')

    assert result.returncode == 0, result.stderr
    # line 3 is `if x != x:`: the solver answered unsat for its true side
    assert {
        "file": UNTAKEN_FILE,
        "lines": [4],
        "reason": "not taken",
        "condition": condition(UNTAKEN_FILE, 3, 7, True),
        "tries": {**NO_TRIES, "unsat": 1},
    } in why_uncovered(result.stdout)


# see-why-a-line-was-missed-says-a-fork-was-not-tried
def test_says_a_fork_was_not_tried() -> None:
    result = run_pyct(NOT_TRIED, '{"x": 0, "y": 0}', "--plateau", "1")

    assert result.returncode == 0, result.stderr
    summary = summary_line(result.stdout)
    assert summary["stopped"] == "no gain in 1 inputs"
    assert len(input_lines(result.stdout)) == 2
    # the plateau stop spent the `y > 0` fork without solving it
    entry = entry_for(result.stdout, 3)
    assert entry["reason"] == "not taken"
    assert entry["condition"] == condition(NOT_TRIED_FILE, 2, 7, True)
    assert entry["tries"] == {**NO_TRIES, "not_tried": 1}


# see-why-a-line-was-missed-names-a-function-no-input-called
def test_names_a_function_no_input_called() -> None:
    result = run_pyct(UNCALLED, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    assert {
        "file": UNCALLED_FILE,
        "lines": [8, 9],
        "reason": "not called",
        "function": "helper",
    } in why_uncovered(result.stdout)


# see-why-a-line-was-missed-names-where-a-condition-was-lost
def test_names_where_a_condition_was_lost() -> None:
    result = run_pyct(LOST, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    assert seed["downgrades"] == [
        {"name": "__xor__", "count": 1, "file": LOST_FILE, "line": 2, "col": 8}
    ]
    assert f"downgrades __xor__ at {LOST_FILE}:2:8" in result.stderr.splitlines()


# see-why-a-line-was-missed-prints-why-on-stderr
def test_prints_why_on_stderr() -> None:
    result = run_pyct(UNTAKEN, '{"x": 2}')

    assert result.returncode == 0, result.stderr
    trace = result.stderr.splitlines()
    why = f"why 4 in {UNTAKEN_FILE}: {UNTAKEN_FILE}:3:7 never true: 1 unsat"
    # the import ran the def line, so line 4 alone is uncovered
    uncovered = trace.index(f"uncovered 4 in {UNTAKEN_FILE}")
    assert uncovered < trace.index(why) < trace.index("stopped: no fork to flip")


# see-why-a-line-was-missed-says-an-input-left-the-plan
def test_says_an_input_left_the_plan() -> None:
    result = run_pyct(LEFT, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert lines[1]["mismatch_at"] == 0
    entry = entry_for(result.stdout, 5)
    assert entry["reason"] == "not taken"
    assert entry["condition"] == condition(LEFT_FILE, 3, 7, False)
    assert entry["tries"] == {**NO_TRIES, "left_the_plan": 1}


# see-why-a-line-was-missed-says-a-plain-condition-recorded-no-fork
def test_says_a_plain_condition_recorded_no_fork() -> None:
    result = run_pyct(PLAIN, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    assert {
        "file": PLAIN_FILE,
        "lines": [4],
        "reason": "no fork",
        "condition": condition(PLAIN_FILE, 3, 7, True),
    } in why_uncovered(result.stdout)
    why = f"why 4 in {PLAIN_FILE}: {PLAIN_FILE}:3:7 never true, no fork"
    assert why in result.stderr.splitlines()


# see-why-a-line-was-missed-blames-the-first-untaken-side-on-the-way
def test_blames_the_first_untaken_side_on_the_way() -> None:
    result = run_pyct(NESTED, '{"x": 0, "y": 0}')

    assert result.returncode == 0, result.stderr
    entry = entry_for(result.stdout, 4)
    assert entry["lines"] == [4, 5]
    assert entry["reason"] == "not taken"
    assert entry["condition"] == condition(NESTED_FILE, 3, 7, True)
    named = [entry.get("condition") for entry in why_uncovered(result.stdout)]
    assert all(line is None or line["line"] != 4 for line in named)  # type: ignore[index]


# see-why-a-line-was-missed-follows-the-way-past-an-early-return
def test_follows_the_way_past_an_early_return() -> None:
    result = run_pyct(EARLY, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    entry = entry_for(result.stdout, 5)
    assert entry["reason"] == "not taken"
    assert entry["condition"] == condition(EARLY_FILE, 3, 7, False)
    assert entry["tries"] == {**NO_TRIES, "unsat": 1}


# see-why-a-line-was-missed-puts-the-lines-after-a-raising-operation-on-its-fork
def test_puts_the_lines_after_a_raising_operation_on_its_fork() -> None:
    result = run_pyct(DIVIDES, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    entry = entry_for(result.stdout, 3)
    assert entry["reason"] == "not taken"
    # the zero fork sits where the division runs, on line 2
    named = entry["condition"]
    assert isinstance(named, dict)
    assert (named["file"], named["line"], named["side"]) == (DIVIDES_FILE, 2, True)
    assert entry["tries"] == {**NO_TRIES, "unsat": 1}


# see-why-a-line-was-missed-says-a-handler-no-raise-reached
def test_says_a_handler_no_raise_reached() -> None:
    result = run_pyct(HANDLER, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    entry = entry_for(result.stdout, 5)
    assert entry["reason"] == "handler"
    why = f"in {HANDLER_FILE}: in a handler no raise reached"
    assert any(
        line.startswith("why ") and line.endswith(why) for line in result.stderr.splitlines()
    )


# see-why-a-line-was-missed-says-inputs-ended-before-a-line
def test_says_inputs_ended_before_a_line() -> None:
    result = run_pyct(ENDS, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    assert {"file": ENDS_FILE, "lines": [3], "reason": "ended before"} in why_uncovered(
        result.stdout
    )
    why = f"why 3 in {ENDS_FILE}: every input that got there ended before it"
    assert why in result.stderr.splitlines()


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


# see-why-a-line-was-missed-accounts-for-every-uncovered-line-once
def test_accounts_for_every_uncovered_line_once() -> None:
    # run_pyct checks every summary line the acceptance suite reads, so each target the suite
    # runs is held to this; these three reach import, not called, handler and not taken at once
    for target, seed in [
        (UNCALLED, '{"x": 1}'),
        (HANDLER, '{"x": 1}'),
        (NESTED, '{"x": 0, "y": 0}'),
    ]:
        result = run_pyct(target, seed)

        assert result.returncode == 0, result.stderr
        assert why_uncovered(result.stdout)


# see-why-a-line-was-missed-explains-a-run-the-solver-ended
def test_explains_a_run_the_solver_ended(tmp_path: Path) -> None:
    solver_failing_second(tmp_path)

    result = run_pyct(TWO_GUARDS, '{"x": 0, "y": 0}', path=str(tmp_path))

    assert result.returncode == 1, result.stderr
    summary = summary_line(result.stdout)
    assert summary["stopped"] == "solver failed"
    # the deepest fork, `y > 0`, was solved first; `x > 0` was being solved when cvc5 failed
    entry = entry_for(result.stdout, 3)
    assert entry["reason"] == "not taken"
    assert entry["condition"] == condition(TWO_GUARDS_FILE, 2, 7, True)
    assert entry["tries"] == {**NO_TRIES, "not_tried": 1}


def solver_failing_second(tmp_path: Path) -> Path:
    """A cvc5 that answers the first formula as the real one does and fails on every later one."""
    real = shutil.which("cvc5")
    assert real is not None, "cvc5 must be on PATH, as for every run"
    count = tmp_path / "solves"
    script = tmp_path / "cvc5"
    script.write_text(
        "#!/bin/sh\n"
        "PATH=/bin:/usr/bin\n"
        f'if [ "$1" = "--version" ]; then exec {real} "$@"; fi\n'
        f"n=$(cat {count} 2>/dev/null || echo 0)\n"
        f"echo $((n + 1)) > {count}\n"
        f'if [ "$n" -ge 1 ]; then cat > /dev/null; echo "cvc5: failed" >&2; exit 1; fi\n'
        f'exec {real} "$@"\n'
    )
    script.chmod(0o755)
    return script
