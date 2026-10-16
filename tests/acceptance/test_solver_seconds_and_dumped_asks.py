"""Acceptance tests for part D of the match-pyct-v1-on-the-measured-functions story.

Each input line, each miss and the summary say how long the solver's asks took, stderr says
it too, and ``--dump-formulas DIR`` writes each program pyct gives cvc5. Each test spawns
``python -P -m pyct`` through the harness and reads stdout, stderr and the files as a person or a
tool reads them after a run.
"""

import re
import subprocess
from pathlib import Path

import pytest

from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct, summary_line

# line 2 `if x > 0:` the solver flips sat; line 3 `if x < 0:` under it, which it answers unsat
NESTED = "targets.asks.sat_then_unsat::nested"
NESTED_FILE = str(REPO_ROOT / "targets" / "asks" / "sat_then_unsat.py")
# line 2 `if x != x:`, which a finite x never takes: the first program, holding x finite, is
# unsat, and a later one of the same ask answers NaN
ODD = "targets.asks.not_a_number::odd"
# line 3 `if t <= s:` under `s < t`, which cvc5 answers unknown at a 1 s limit
ORDER = "targets.flip.order::order"
SECONDS = re.compile(r"\d+\.\d{3}")


def seconds_of(value: object) -> float:
    """A seconds field off a printed line, narrowed so arithmetic on it means something."""
    assert isinstance(value, float | int) and not isinstance(value, bool), value
    assert value >= 0, value
    return float(value)


def nested_run(*argv: str) -> subprocess.CompletedProcess[str]:
    result = run_pyct(NESTED, '{"x": 0}', *argv)
    assert result.returncode == 0, result.stderr
    return result


# match-pyct-v1-on-the-measured-functions-seconds-on-each-line
def test_each_line_and_the_summary_say_the_solver_s_seconds() -> None:
    result = nested_run()

    seed, solved = input_lines(result.stdout)
    assert seed["solver_seconds"] is None
    sat = seconds_of(solved["solver_seconds"])
    summary = summary_line(result.stdout)
    misses = summary["misses"]
    assert isinstance(misses, list) and len(misses) == 1, misses
    unsat = seconds_of(misses[0]["solver_seconds"])
    totals = summary["solver_seconds"]
    assert isinstance(totals, dict)
    assert set(totals) == {"sat", "unsat", "unknown", "timeout"}
    assert abs(seconds_of(totals["sat"]) - sat) <= 0.001
    assert abs(seconds_of(totals["unsat"]) - unsat) <= 0.001
    assert totals["unknown"] == totals["timeout"] == 0


# match-pyct-v1-on-the-measured-functions-seconds-on-each-line
def test_stderr_says_each_ask_s_seconds_and_their_sums() -> None:
    result = nested_run()

    lines = result.stderr.splitlines()
    aim = next(i for i, line in enumerate(lines) if line.startswith("aim "))
    assert re.fullmatch(r"asked in \d+\.\d{3} s", lines[aim + 1]), lines[aim : aim + 2]
    missed = next(line for line in lines if line.startswith("missed "))
    assert re.fullmatch(rf"missed {re.escape(NESTED_FILE)}:3:11 unsat after \d+\.\d{{3}} s", missed)
    solver = lines.index("solver: 1 sat, 1 unsat, 0 unknown, 0 timeout")
    pattern = r"solver seconds: \d+\.\d{3} sat, \d+\.\d{3} unsat, 0\.000 unknown, 0\.000 timeout"
    assert re.fullmatch(pattern, lines[solver + 1]), lines[solver + 1]


def dumped(directory: Path) -> list[str]:
    """The files in the dump directory, in the order pyct numbered them."""

    def number(name: str) -> tuple[int, int]:
        parts = name.removeprefix("ask-").removesuffix(".smt2").split("-")
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 1

    return sorted((path.name for path in directory.iterdir()), key=number)


def answered_by_cvc5(path: Path) -> str:
    """What cvc5 answers when it runs the file as written."""
    ran = subprocess.run(["cvc5", str(path)], capture_output=True, text=True, check=False)
    return ran.stdout.splitlines()[0]


# match-pyct-v1-on-the-measured-functions-dump-writes-each-ask
def test_dump_writes_each_ask_cvc5_can_run(tmp_path: Path) -> None:
    directory = tmp_path / "D"
    directory.mkdir()

    nested_run("--dump-formulas", str(directory))

    assert dumped(directory) == ["ask-1.smt2", "ask-2.smt2"]
    # the seed's fork on line 2, then the fork under it, second on the solver input's path
    asks = (
        ("ask-1.smt2", "2:7 at position 0, on the path of stdout line 1", "sat"),
        ("ask-2.smt2", "3:11 at position 1, on the path of stdout line 2", "unsat"),
    )
    for name, aim, answer in asks:
        head = (directory / name).read_text().splitlines()[:2]
        assert head[0] == f"; aim {NESTED_FILE}:{aim}", head
        assert re.fullmatch(rf"; cvc5 answered {answer} in \d+\.\d{{3}} s", head[1]), head
        assert answered_by_cvc5(directory / name) == answer


# match-pyct-v1-on-the-measured-functions-dump-writes-each-ask
def test_dump_names_cvc5_s_own_word_and_pyct_s_reading_when_they_differ(tmp_path: Path) -> None:
    directory = tmp_path / "D"

    result = run_pyct(
        ORDER, '{"s": "a", "t": "b"}', "--solver-timeout", "1", "--dump-formulas", str(directory)
    )

    assert result.returncode == 0, result.stderr
    timed_out = [
        name
        for name in dumped(directory)
        if "; cvc5 answered unknown (timeout) in " in (directory / name).read_text()
    ]
    # cvc5 answers unknown at its limit, which pyct reads as a timeout
    assert timed_out, dumped(directory)
    assert answered_by_cvc5(directory / timed_out[0]) == "unknown"


# match-pyct-v1-on-the-measured-functions-dump-numbers-each-program-of-an-ask
def test_dump_numbers_each_program_of_one_ask(tmp_path: Path) -> None:
    directory = tmp_path / "D"

    result = run_pyct(ODD, '{"x": 0.0}', "--dump-formulas", str(directory))

    assert result.returncode == 0, result.stderr
    names = dumped(directory)
    assert names[:2] == ["ask-1.smt2", "ask-1-2.smt2"], names
    assert names == ["ask-1.smt2", *(f"ask-1-{k}.smt2" for k in range(2, len(names) + 1))]
    answers = [answered_by_cvc5(directory / name) for name in names]
    assert answers[0] == "unsat" and answers[-1] == "sat", answers


# match-pyct-v1-on-the-measured-functions-dump-only-with-the-flag
def test_no_file_without_the_flag(tmp_path: Path) -> None:
    (tmp_path / "nested.py").write_text((REPO_ROOT / NESTED_FILE).read_text())

    result = run_pyct("nested::nested", '{"x": 0}', cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert [path.name for path in tmp_path.rglob("*.smt2")] == []


def refused(path: Path) -> subprocess.CompletedProcess[str]:
    result = run_pyct(NESTED, '{"x": 0}', "--dump-formulas", str(path))
    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert str(path) in result.stderr
    return result


# match-pyct-v1-on-the-measured-functions-dump-refuses-an-unusable-directory
def test_dump_refuses_a_file(tmp_path: Path) -> None:
    path = tmp_path / "D"
    path.write_text("")

    assert "not a directory" in refused(path).stderr


# match-pyct-v1-on-the-measured-functions-dump-refuses-an-unusable-directory
def test_dump_refuses_a_directory_that_holds_files(tmp_path: Path) -> None:
    (tmp_path / "old.smt2").write_text("")

    assert "already holds files" in refused(tmp_path).stderr


# match-pyct-v1-on-the-measured-functions-dump-refuses-an-unusable-directory
@pytest.mark.parametrize("make", [False, True])
def test_dump_refuses_a_directory_it_cannot_create_or_write(tmp_path: Path, make: bool) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    path = locked / "D"
    if make:
        path.mkdir()
        path.chmod(0o500)
    else:
        locked.chmod(0o500)
    try:
        result = refused(path)
    finally:
        locked.chmod(0o700)
        if path.exists():
            path.chmod(0o700)
    assert "cannot" in result.stderr
    # the target never ran: no line, and nothing written
    assert not path.exists() or list(path.iterdir()) == []
