"""Summaries' form check of the reply's code, how stderr writes a formula, and the two checks a
formula runs through in forked children: on the past runs in plain Python, and for values pyct
follows."""

import pytest

from pyct.core.foundation.branch import Changed, GoingIn, PieceRun, Site
from pyct.intercept.model_code import Refused
from pyct.run import model_runs
from pyct.run.summary_checks import (
    CompleteRun,
    Ended,
    Formula,
    check_formula,
    formula_code,
)

SITE = Site("/t/m.py", 10, 4)
PARAMETERS = ("s", "t")


@pytest.fixture(autouse=True)
def one_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model_runs, "running", lambda: 1)


def read(code: str, parameters: tuple[str, ...] = PARAMETERS, changed: tuple[str, ...] = ("t",)):
    return formula_code(code, parameters, changed, "<summary m:10:4>")


def refusal(code: str) -> str:
    found = read(code)
    assert isinstance(found, Refused)
    return found.reason


def run_of(number: int, s: str, t: int = 0, *, tracked: bool = True) -> CompleteRun:
    going_in = (GoingIn("s", f'"{s}"', tracked), GoingIn("t", str(t), False))
    return CompleteRun(number, PieceRun(SITE, going_in, (Changed("t", str(t + s.count("z"))),)))


RUNS = (run_of(1, "ab"), run_of(2, "zz"), run_of(4, "az", 1))


def checked(code: str, runs: tuple[CompleteRun, ...] = RUNS) -> str | Ended | None:
    formula = read(code)
    assert isinstance(formula, Formula), formula
    return check_formula(formula.code, runs, PARAMETERS, ("t",), None)


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("import os\ndef summary(s, t):\n    return {'t': t}", "a formula may not import"),
        ("x = 1", "the code must define one function, summary, and nothing else"),
        ("def f(s, t):\n    return {'t': t}", "a formula may not define f"),
        (
            "def summary(s, t):\n    return {'t': t}\ndef condition(s, t):\n    return True",
            "a formula may not define condition",
        ),
        ("def summary(s):\n    return {'t': 0}", "summary must take exactly the parameters s, t"),
        (
            "def summary(s, t=0):\n    return {'t': t}",
            "summary must take exactly the parameters s, t",
        ),
        (
            "def summary(s, t):\n    for c in s:\n        t += 1\n    return {'t': t}",
            "a formula may not use a loop",
        ),
        (
            "def summary(s, t):\n    def g():\n        return 1\n    return {'t': t}",
            "a formula may not define g",
        ),
        (
            "def summary(s, t):\n" + "    t = t\n" * 10 + "    return {'t': t}",
            "a formula may hold at most 10 statements",
        ),
        (
            "def summary(s, t):\n    return {'u': t}",
            'summary must end by returning a dict with one entry for each of "t"',
        ),
        (
            "def summary(s, t):\n    return t",
            'summary must end by returning a dict with one entry for each of "t"',
        ),
        (
            "def summary(s, t):\n    return {'t': t, 't': 1}",
            'summary must end by returning a dict with one entry for each of "t"',
        ),
        (
            "def summary(s, t):\n    return {'t': [c for c in s]}",
            "a formula may not use a comprehension",
        ),
        (
            "def summary(s, t):\n    return {'t': max([lambda: 1])}",
            "a formula may not use a lambda",
        ),
        ("def summary(s, t):\n    return {'t': summary(s, t)}", "a formula may not call summary"),
        ("def summary(s, t):\n    return {'t': s.__len__()}", "a formula may not call __len__"),
        ("def summary(s, t):\n    return {'t': '{}'.format(s)}", "a formula may not call format"),
        (
            "def summary(s, t):\n    return {'t': s.real}",
            "a formula may not read the attribute real",
        ),
        ("def summary(s, t):\n    return {'t': u}", "a formula may not read u"),
        (
            "def summary(s, t):\n    return {'t': math.pi}",
            "a formula may not read the attribute pi",
        ),
        (
            "def summary(s, t):\n    x, y = 1, 2\n    return {'t': t}",
            "a formula assigns only to names",
        ),
        (
            "def summary(s, t):\n    if t:\n        return {'t': 1}\n    return {'t': t}",
            "a formula returns only as its last statement",
        ),
        (
            "def summary(s, t):\n    pass\n    return {'t': t}",
            "a formula may not use a Pass statement",
        ),
        ("def summary(s, t)\n    return {'t': t}", "does not parse"),
    ],
)
def test_the_form_check_refuses_with_one_short_reason(code: str, reason: str) -> None:
    assert refusal(code).startswith(reason)


def test_a_formula_may_assign_branch_and_call_math_and_the_listed_builtins() -> None:
    code = (
        "def summary(s, t):\n"
        "    n = len(s)\n"
        "    if n > 3:\n"
        "        n = min(n, 3)\n"
        "    else:\n"
        "        n += sum([1, 2])\n"
        "    return {'t': math.floor(t + n)}"
    )

    assert isinstance(read(code), Formula)


def test_one_return_is_written_name_by_name_as_the_reply_wrote_each_value() -> None:
    formula = read(
        "def summary(s, ups, downs):\n    return {'ups': ups+1, \"downs\": downs  * 2}",
        ("s", "ups", "downs"),
        ("downs", "ups"),
    )

    assert isinstance(formula, Formula)
    assert (formula.text, formula.below) == ("ups = ups+1; downs = downs  * 2", False)


def test_more_statements_are_written_below_as_the_reply_wrote_them() -> None:
    formula = read("def summary(s, t):\n    n = len(s)\n    return {'t': t + n}")

    assert isinstance(formula, Formula)
    assert (formula.text, formula.below) == ("n = len(s)\nreturn {'t': t + n}", True)


def test_a_formula_that_gives_every_recorded_value_and_a_tracked_one_passes() -> None:
    assert checked("def summary(s, t):\n    return {'t': t + s.count('z')}") is None


def test_the_first_value_that_is_not_the_recorded_one_fails_the_check() -> None:
    reason = checked("def summary(s, t):\n    return {'t': s.count('z')}")

    assert reason == "at input 4, t was 2, the formula gave 1"


def test_a_value_json_cannot_hold_is_named_by_its_kind() -> None:
    reason = checked("def summary(s, t):\n    return {'t': s.partition('a')}")

    assert reason == "at input 1, t was 0, the formula gave a tuple"


def test_a_raise_on_a_past_run_names_its_input() -> None:
    reason = checked("def summary(s, t):\n    return {'t': t + 1 // (len(s) - 2)}")

    assert reason == "it raised at input 1: ZeroDivisionError: integer division or modulo by zero"


def test_a_formula_that_does_not_finish_fails_the_check() -> None:
    reason = checked("def summary(s, t):\n    return {'t': math.factorial(10 ** 7)}")

    assert isinstance(reason, str)
    assert reason.startswith("it did not finish on the past runs: ")


def test_a_value_pyct_does_not_follow_names_the_operation() -> None:
    reason = checked("def summary(s, t):\n    return {'t': t + s.lower().encode().count(b'z')}")

    assert reason == "pyct does not follow encode"


def test_a_value_built_from_untracked_names_alone_is_not_tracked() -> None:
    runs = (run_of(1, "ab", tracked=False), run_of(2, "zz", tracked=False))

    reason = checked("def summary(s, t):\n    return {'t': t + s.count('z')}", runs)

    assert reason == "t is not tracked"


def test_no_check_runs_beside_a_second_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model_runs, "running", lambda: 2)

    assert checked("def summary(s, t):\n    return {'t': t}") == Ended("cannot fork")
