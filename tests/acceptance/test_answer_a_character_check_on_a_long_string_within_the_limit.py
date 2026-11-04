"""Acceptance tests for answer-a-character-check-on-a-long-string-within-the-limit: the checks a
loop makes on each character of a string are answered within the solver's limit, and keep
their answers.

Each test spawns ``python -P -m pyct`` through the harness, so the asks are the ones a run
writes.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from pyct.config.solver_timeout import DEFAULT_SECONDS
from tests.acceptance.harness import REPO_ROOT, run_pyct, summary_line

CAMEL = "targets.strs.camel_to_snake::camel_to_snake_case"
CAMEL_FILE = REPO_ROOT / "targets" / "strs" / "camel_to_snake.py"
UPPER_AND_DIGIT = "targets.strs.upper_and_digit::both"
UPPER_AND_DIGIT_FILE = str(REPO_ROOT / "targets" / "strs" / "upper_and_digit.py")

# the solver limit, in the milliseconds a dumped program's `:tlimit-per` gives cvc5
SOLVER_LIMIT_MS = round(DEFAULT_SECONDS * 1000)

# pyct writes a solve's first program within milliseconds of the solve's start, 14 ms at most
# in the runs here, so a first program given more than a second less than the solver limit was
# given what was left of the budget. A solve's later programs share the solve's own limit, so a
# short limit on one of them says nothing about the budget
WRITING_MS = 1000

# how a program that ran out of its time reads: cvc5 at its limit, or pyct stopping it past it
RAN_OUT = {"unknown (timeout)", "no answer (timeout)"}


# answer-a-character-check-on-a-long-string-within-the-limit-keeps-a-contradiction-unsat
def test_an_uppercase_digit_stays_unsat() -> None:
    # the loop lengthens the string with each pass, so the run ends on its plateau, about 1 s
    # in, long before the budget's end could cut an ask short
    argv = ("--budget", "30", "--plateau", "40")
    result = run_pyct(UPPER_AND_DIGIT, '{"s": "aB1"}', *argv, timeout=60)

    assert result.returncode == 0, result.stderr
    summary = summary_line(result.stdout)
    assert summary["stopped"] == "no gain in 40 inputs", summary
    assert summary["uncovered"] == {UPPER_AND_DIGIT_FILE: [4]}, summary
    # each flip into `return 1` makes `c.isdigit()` true on an uppercase character
    explained = summary["why_uncovered"]
    assert isinstance(explained, list) and len(explained) == 1, explained
    why = explained[0]
    condition = {"file": UPPER_AND_DIGIT_FILE, "line": 3, "col": 27, "side": True}
    assert why["condition"] == condition, why
    tries = why["tries"]
    assert tries["unsat"] > 0, why
    assert [tries[kind] for kind in ("unknown", "timeout", "left_the_plan", "decided")] == [0] * 4
    misses = summary["misses"]
    assert isinstance(misses, list)
    assert {miss["why"] for miss in misses if miss["line"] == 3 and miss["col"] == 27} == {"unsat"}


def line_of(statement: str) -> tuple[int, str]:
    """The camel-case target's one line that is the statement, and the line as written."""
    lines = CAMEL_FILE.read_text().splitlines()
    (number,) = [at for at, line in enumerate(lines, 1) if line.strip() == statement]
    return number, lines[number - 1]


def camel_run(seed: str, directory: Path) -> dict[str, object]:
    """The summary of a 30 s run on the camel-case target from the seed, its asks dumped."""
    argv = ("--budget", "30", "--dump-formulas", str(directory))
    result = run_pyct(CAMEL, f'{{"input_str": "{seed}"}}', *argv, timeout=90)
    assert result.returncode == 0, result.stderr
    return summary_line(result.stdout)


@dataclass(frozen=True)
class Asked:
    """A dumped program: its ask's place in the run's order, what cvc5 answered, and the
    milliseconds it was given."""

    order: tuple[int, ...]
    answer: str
    limit_ms: int

    @property
    def cut_by_the_budget(self) -> bool:
        """Whether the program is its solve's first and was given what was left of the budget,
        short of the limit."""
        return len(self.order) == 1 and self.limit_ms < SOLVER_LIMIT_MS - WRITING_MS


def asked_at_alnum(directory: Path) -> list[Asked]:
    """Each program asked at `not char.isalnum()` from the seed's path, in the run's order."""
    line, written = line_of("elif not char.isalnum():")
    aim = f"; aim {CAMEL_FILE}:{line}:{written.index('char.isalnum()')} at position "
    asked = []
    for path in directory.glob("ask-*.smt2"):
        text = path.read_text()
        head = text.splitlines()[:2]
        if head[0].startswith(aim) and head[0].endswith(", on the path of stdout line 1"):
            answered = re.fullmatch(r"; cvc5 answered (.+) in \d+\.\d{3} s", head[1])
            limit = re.search(r"^\(set-option :tlimit-per (\d+)\)$", text, re.MULTILINE)
            assert answered is not None and limit is not None, head
            order = tuple(int(part) for part in path.stem.split("-")[1:])
            asked.append(Asked(order, answered.group(1), int(limit.group(1))))
    return sorted(asked, key=lambda program: program.order)


def assert_answered_within_the_limit(directory: Path, answers: set[str]) -> None:
    """The seed's path's first ask at `not char.isalnum()`, the one the run makes first, was
    given the solver limit and answered one of the answers, and so did every later one.

    A later ask the budget's end gave less than the limit and that ran out says nothing about
    the limit: it ran out of the budget.
    """
    asked = asked_at_alnum(directory)
    assert asked, sorted(path.name for path in directory.iterdir())
    first, *rest = asked
    assert not first.cut_by_the_budget and first.answer in answers, first
    ran_out = [
        program
        for program in rest
        if program.answer not in answers
        and not (program.cut_by_the_budget and program.answer in RAN_OUT)
    ]
    assert ran_out == []


# answer-a-character-check-on-a-long-string-within-the-limit-covers-camel-case-line-45
@pytest.mark.serial
def test_a_character_that_is_not_alphanumeric_reaches_its_line(tmp_path: Path) -> None:
    summary = camel_run("someRandomString", tmp_path / "D")

    covered = summary["covered"]
    assert isinstance(covered, dict), summary
    assert line_of('snake_str += "_"')[0] in covered[str(CAMEL_FILE)], summary
    assert_answered_within_the_limit(tmp_path / "D", {"sat"})


# answer-a-character-check-on-a-long-string-within-the-limit-answers-a-long-loop
@pytest.mark.serial
def test_answers_the_check_on_a_64_character_loop(tmp_path: Path) -> None:
    camel_run("someRandom123Str" * 4, tmp_path / "D")

    assert_answered_within_the_limit(tmp_path / "D", {"sat", "unsat"})
