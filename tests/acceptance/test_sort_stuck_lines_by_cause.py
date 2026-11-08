"""Acceptance tests for the sort-stuck-lines-by-cause story.

Each test spawns ``python -P -m pyct`` through the harness and reads the summary line's
``why_uncovered``, an input's downgrade entries, or the stderr trace, as a person or sweep
would read them after a run.
"""

from pathlib import Path

from tests.acceptance.harness import REPO_ROOT, downgrade, first_line, run_pyct, summary_line

FILE = str(REPO_ROOT / "targets" / "why" / "stuck.py")
SHORT = ("--plateau", "3")
SCOPE = REPO_ROOT / "targets" / "scope"
PARSED = "targets/scope/shop/parsed.py"


def target(function: str) -> str:
    return f"targets.why.stuck::{function}"


def line_of(text: str) -> int:
    """The line of the target file that holds ``text``, the first such."""
    lines = Path(FILE).read_text(encoding="utf-8").splitlines()
    return next(number for number, line in enumerate(lines, 1) if text in line)


def col_of(text: str) -> int:
    """The column ``text`` starts at on its line."""
    return Path(FILE).read_text(encoding="utf-8").splitlines()[line_of(text) - 1].index(text)


def entry_for(stdout: str, line: int) -> dict[str, object]:
    """The one cause whose lines hold ``line``."""
    entries = summary_line(stdout)["why_uncovered"]
    assert isinstance(entries, list), stdout
    holding = [entry for entry in entries if line in entry["lines"]]
    assert len(holding) == 1, entries
    return holding[0]


def why_line(stderr: str, line: int) -> str:
    """The stderr ``why`` line for the cause that holds ``line``, alone of its lines."""
    start = f"why {line} in {FILE}: "
    found = [each for each in stderr.splitlines() if each.startswith(start)]
    assert len(found) == 1, stderr
    return found[0]


def downgrades_of(stdout: str) -> list[dict[str, object]]:
    downgrades = first_line(stdout)["downgrades"]
    assert isinstance(downgrades, list), stdout
    return downgrades


# run-missed-line-source-loop-names-the-loop-that-changed-a-name
def test_names_the_loop_that_changed_a_name() -> None:
    result = run_pyct(target("counts"), '{"s": "ab"}', *SHORT)

    assert result.returncode == 0, result.stderr
    many, loop = line_of('return "many"'), line_of("for c in s:")
    entry = entry_for(result.stdout, many)
    assert entry["reason"] == "no fork"
    assert entry["condition"] == {"file": FILE, "line": many - 1, "col": 7, "side": True}
    assert entry["sources"] == [{"kind": "loop", "name": "t", "file": FILE, "line": loop, "col": 4}]
    assert why_line(result.stderr, many).endswith(f"; t came from the loop at {FILE}:{loop}")


# run-missed-line-source-loop-counts-a-comprehension-as-a-loop
def test_counts_a_comprehension_as_a_loop() -> None:
    result = run_pyct(target("counted"), '{"s": "ab"}', *SHORT)

    assert result.returncode == 0, result.stderr
    summed = "(1 for c in s if c == "
    entry = entry_for(result.stdout, line_of("t = sum(") + 2)
    assert entry["sources"] == [
        {"kind": "loop", "name": "t", "file": FILE, "line": line_of(summed), "col": col_of(summed)}
    ]


# run-missed-line-source-call-names-the-call-that-lost-a-value
def test_names_the_call_that_lost_a_value() -> None:
    result = run_pyct(target("ones"), '{"x": 3}', *SHORT)

    assert result.returncode == 0, result.stderr
    seven, at = line_of('return "seven"'), line_of('bin(x).count("1")')
    entry = entry_for(result.stdout, seven)
    assert entry["reason"] == "no fork"
    lost = {"kind": "lost", "name": "x", "call": "bin", "file": FILE, "line": at, "col": 7}
    assert entry["sources"] == [lost]
    assert why_line(result.stderr, seven).endswith(f"; x lost in bin at {FILE}:{at}:7")


# run-missed-line-source-call-follows-a-name-back-to-the-call
def test_follows_a_name_back_to_the_call() -> None:
    result = run_pyct(target("zeros"), '{"x": 3}', *SHORT)

    assert result.returncode == 0, result.stderr
    at = line_of("y = bin(x)")
    entry = entry_for(result.stdout, line_of('return "three"'))
    lost = {"kind": "lost", "name": "x", "call": "bin", "file": FILE, "line": at, "col": 8}
    assert entry["sources"] == [lost]


# run-missed-line-no-source-finds-no-source-through-an-attribute
def test_finds_no_source_through_an_attribute() -> None:
    result = run_pyct(target("boxed"), '{"x": 3}', *SHORT)

    assert result.returncode == 0, result.stderr
    seven = line_of("if box.size == 7:") + 1
    entry = entry_for(result.stdout, seven)
    assert entry["reason"] == "no fork"
    assert entry["sources"] == []
    assert why_line(result.stderr, seven).endswith("; no source found")


# run-missed-line-no-source-keeps-other-causes-as-they-were
def test_keeps_other_causes_as_they_were() -> None:
    untaken = run_pyct("targets.why.untaken::same", '{"x": 2}')
    uncalled = run_pyct(target("typed"), '{"x": 3}', *SHORT)

    assert untaken.returncode == 0, untaken.stderr
    assert uncalled.returncode == 0, uncalled.stderr
    entries = [
        entry
        for result in (untaken, uncalled)
        for entry in summary_line(result.stdout)["why_uncovered"]  # type: ignore[union-attr]
        if entry["reason"] != "no fork"
    ]
    assert {entry["reason"] for entry in entries} == {"not taken", "not called"}, entries
    assert all("sources" not in entry for entry in entries), entries


# run-quiet-loss-downgrade-records-a-quiet-loss
def test_records_a_quiet_loss() -> None:
    result = run_pyct(target("ones"), '{"x": 3}', *SHORT)

    assert result.returncode == 0, result.stderr
    at = line_of('bin(x).count("1")')
    assert downgrades_of(result.stdout) == [downgrade("bin", 1, f"targets/why/stuck.py:{at}:7")]
    assert f"downgrades bin at {FILE}:{at}:7" in result.stderr.splitlines()


# run-quiet-loss-downgrade-names-a-call-as-written
def test_names_a_call_as_written() -> None:
    # `parse` is the library's, beside the target's package
    result = run_pyct("shop.parsed::parsed", '{"x": 3}', *SHORT, cwd=SCOPE)

    assert result.returncode == 0, result.stderr
    assert downgrades_of(result.stdout) == [downgrade("parse", 1, f"{PARSED}:5:7")]


# run-quiet-loss-downgrade-judges-no-call-into-the-target-s-package
def test_judges_no_call_into_the_target_s_package() -> None:
    result = run_pyct(target("judged"), '{"x": 3}', *SHORT)

    assert result.returncode == 0, result.stderr
    line = first_line(result.stdout)
    at = line_of("if v > 100:")
    forks = line["forks"]
    assert isinstance(forks, list), line
    assert [(fork["file"], fork["line"], fork["col"]) for fork in forks] == [(FILE, at, 7)]
    assert downgrades_of(result.stdout) == []


# run-quiet-loss-downgrade-reads-a-container-passed-to-the-call
def test_reads_a_container_passed_to_the_call() -> None:
    result = run_pyct(target("packed"), '{"x": 3}', *SHORT)

    assert result.returncode == 0, result.stderr
    at = line_of("if bytes([x % 256, 1])[0] == 7:")
    assert downgrades_of(result.stdout) == [downgrade("bytes", 1, f"targets/why/stuck.py:{at}:7")]


# run-quiet-loss-downgrade-records-no-loss-for-type-or-none
def test_records_no_loss_for_type_or_none() -> None:
    result = run_pyct(target("typed"), '{"x": 3}', *SHORT)

    assert result.returncode == 0, result.stderr
    assert downgrades_of(result.stdout) == []


# run-quiet-loss-downgrade-records-one-downgrade-for-a-call-that-lost-inside
def test_records_one_downgrade_for_a_call_that_lost_inside() -> None:
    result = run_pyct(target("lost_inside"), '{"x": 3}', *SHORT)

    assert result.returncode == 0, result.stderr
    at = line_of("return v ^ 0")
    assert downgrades_of(result.stdout) == [
        downgrade("__xor__", 1, f"targets/why/stuck.py:{at}:11")
    ]


# run-quiet-loss-downgrade-leaves-an-operator-loss-silent
def test_leaves_an_operator_loss_silent() -> None:
    result = run_pyct(target("picked"), '{"x": 3}', *SHORT)

    assert result.returncode == 0, result.stderr
    assert downgrades_of(result.stdout) == []
