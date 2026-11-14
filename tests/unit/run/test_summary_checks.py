"""Summaries' form check of the reply's code, how stderr writes a formula, and the two checks a
formula runs through in forked children: on the past runs in plain Python, and for values pyct
follows."""

import ast
import json
import time
from pathlib import Path

import pytest

from pyct.core.foundation.branch import Changed, GoingIn, PieceRun, Site
from pyct.execution.blame import one_line
from pyct.intercept.model_code import Refused
from pyct.run import model_runs
from pyct.run.summary_checks import (
    CompleteRun,
    Ended,
    Formula,
    check_formula,
    formula_code,
)
from pyct.run.summary_form import FormCheck

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


def checked(
    code: str, runs: tuple[CompleteRun, ...] = RUNS, until: float | None = None
) -> str | Ended | None:
    formula = read(code)
    assert isinstance(formula, Formula), formula
    return check_formula(formula.code, runs, PARAMETERS, ("t",), until)


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
        ("def summary(s, t)\n    return {'t': t}", "does not parse"),
    ],
)
def test_the_form_check_refuses_with_one_short_reason(code: str, reason: str) -> None:
    assert refusal(code).startswith(reason)


BODY = "    return {'t': t + s.count('z')}"
ONE_FUNCTION = "the code must define one function, summary, and nothing else"


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        ("def summary(s: int, t):", "a formula may not annotate its parameters"),
        ("def summary(s, t) -> dict:", "a formula may not annotate its return"),
        ("def summary[T](s: T, t):", "a formula may not take type parameters"),
        ("def summary[T: int](s, t):", "a formula may not take type parameters"),
        ("def summary[*T](s, t):", "a formula may not take type parameters"),
        ("def summary(s, t=0):", "summary must take exactly the parameters s, t"),
        ("def summary(s, *, t=0):", "summary must take exactly the parameters s, t"),
        ("def summary(s, /, t):", "summary must take exactly the parameters s, t"),
        ("def summary(s, t, *a: int):", "summary must take exactly the parameters s, t"),
        ("def summary(s, t, **k: int):", "summary must take exactly the parameters s, t"),
        ("@max\ndef summary(s, t):", "a formula may not use a decorator"),
        ("async def summary(s, t):", ONE_FUNCTION),
    ],
)
def test_the_def_line_holds_the_name_and_the_bare_parameters_alone(line: str, reason: str) -> None:
    assert refusal(f"{line}\n{BODY}") == reason


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        (f"def summary(s, t):\n{BODY}\nx = 1", "the code must define one function, summary,"),
        (f"def summary(s, t):\n    x = yield 1\n{BODY}", "a formula may not use Yield"),
        (f"def summary(s, t):\n    x = (y := len(s))\n{BODY}", "a formula may not use an assign"),
        (f"def summary(s, t):\n    s.x = 1\n{BODY}", "a formula assigns only to names"),
        (f"def summary(s, t):\n    s[0] = 1\n{BODY}", "a formula assigns only to names"),
        (f"def summary(s, t):\n    s[0] += 1\n{BODY}", "a formula assigns only to names"),
        ("def summary(s, t):\n    return {'t': t, **s}", "summary must end by returning a dict"),
        ("def summary(s, t):\n    return {'t': {s: 1}}", "a formula may not use Dict"),
        ("def summary(s, t):\n    return {'t': f'{s:{t}}'}", "a formula may not use JoinedStr"),
        ("def summary(s, t):\n    return {'t': max(*s)}", "a formula may not unpack arguments"),
        ("def summary(s, t):\n    return {'t': s[u]}", "a formula may not read u"),
        ("def summary(s, t):\n    return {'t': s[1:u]}", "a formula may not read u"),
        ("def summary(s, t):\n    return {'t': 0 < t < u}", "a formula may not read u"),
        ("def summary(s, t):\n    return {'t': round(t, ndigits=u)}", "a formula may not read u"),
        ("def summary(s, t):\n    return {'t': [*s]}", "a formula may not use a star"),
    ],
)
def test_each_statement_and_expression_holds_only_what_the_form_reads(
    code: str, reason: str
) -> None:
    assert refusal(code).startswith(reason)


# code that writes a marker file when Python evaluates it
PAYLOAD = "__import__('pathlib').Path({marker!r}).write_text('ran')"


@pytest.mark.parametrize(
    "line",
    [
        "def summary(s: {payload}, t):",
        "def summary(s, t) -> {payload}:",
        "def summary[T](s: {payload}, t):",
        "def summary[T: {payload}](s, t):",
    ],
)
def test_code_in_the_def_line_is_refused_and_never_runs(line: str, tmp_path: Path) -> None:
    marker = tmp_path / "ran"
    code = line.format(payload=PAYLOAD.format(marker=str(marker))) + "\n" + BODY

    found = read(code)
    if isinstance(found, Formula):
        check_formula(found.code, RUNS, PARAMETERS, ("t",), None)

    assert not marker.exists()
    assert isinstance(found, Refused)


@pytest.mark.parametrize(
    "code",
    [
        f"def summary(s, t):  # type: (int, int) -> dict\n{BODY}",
        f"def summary(\n    s,  # type: int\n    t,\n):\n{BODY}",
        f"def summary(s, t):\n    x = 1  # type: int\n{BODY}",
        f"def summary(s, t):  # type: ignore\n{BODY}",
    ],
)
def test_a_type_comment_is_refused(code: str) -> None:
    check = FormCheck(PARAMETERS, ("t",))

    assert check(ast.parse(code, type_comments=True)) == "a formula may not hold a type comment"


class LaterArg(ast.arg):
    """An ``arg`` as a later Python might write it, with a field pyct does not read."""

    _fields = (*ast.arg._fields, "later")


def test_a_field_the_form_check_does_not_read_is_refused() -> None:
    tree = ast.parse(f"def summary(s, t):\n{BODY}")
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef)
    function.args.args[0].__class__ = LaterArg

    reason = FormCheck(PARAMETERS, ("t",))(tree)

    assert reason == "a formula may not use the field arg.later, which pyct does not read"


@pytest.mark.parametrize(
    "code",
    [
        f'def summary(s, t):\n    """Count each z."""\n{BODY}',
        f"def summary(s, t):\n    pass\n{BODY}",
        f'def summary(s, t):\n    """Count each z."""\n    pass\n{BODY}\n    pass',
    ],
)
def test_a_leading_docstring_and_a_pass_are_dropped(code: str) -> None:
    formula = read(code)

    assert isinstance(formula, Formula)
    assert (formula.text, formula.below) == ("t = t + s.count('z')", False)
    assert check_formula(formula.code, RUNS, PARAMETERS, ("t",), None) is None


def test_a_pass_inside_an_if_does_nothing() -> None:
    formula = read(
        f"def summary(s, t):\n    if t > 9:\n        pass\n    else:\n        t = t\n{BODY}"
    )

    assert isinstance(formula, Formula)


@pytest.mark.parametrize(
    ("statement", "reason"),
    [
        ("x: int = 1", "a formula may not annotate a name"),
        ("s.count('z')", "a formula may not use an expression statement"),
        (
            "x = 1\n    'a docstring that does not lead'",
            "a formula may not use an expression statement",
        ),
        ("yield 1", "a formula may not use an expression statement"),
        ("global len", "a formula may not use a global statement"),
        ("nonlocal t", "a formula may not use a nonlocal statement"),
        ("del s", "a formula may not use a del statement"),
        ("assert t", "a formula may not use an assert statement"),
        ("raise ValueError", "a formula may not use a raise statement"),
        (
            "try:\n        x = 1\n    except ValueError:\n        x = 2",
            "a formula may not use a try statement",
        ),
        (
            "try:\n        x = 1\n    except* ValueError:\n        x = 2",
            "a formula may not use a try statement",
        ),
        ("with s:\n        x = 1", "a formula may not use a with statement"),
        ("match t:\n        case 1:\n            x = 1", "a formula may not use a match statement"),
        ("type X = int", "a formula may not use a type statement"),
        ("break", "a formula may not use a break statement"),
        ("continue", "a formula may not use a continue statement"),
    ],
)
def test_a_statement_outside_the_form_is_named_in_words(statement: str, reason: str) -> None:
    assert refusal(f"def summary(s, t):\n    {statement}\n{BODY}") == reason


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
    with pytest.raises(ZeroDivisionError) as plain:
        1 // len("")

    reason = checked("def summary(s, t):\n    return {'t': t + 1 // (len(s) - 2)}")

    assert reason == f"it raised at input 1: {one_line(plain.value)}"


def test_a_correct_formula_passes_on_runs_whose_values_pass_the_answer_s_capacity() -> None:
    def long_run(number: int) -> CompleteRun:
        s = f"{number:04}" + "z" * 2_000
        going_in = (GoingIn("s", json.dumps(s), True), GoingIn("t", '""', False))
        return CompleteRun(number, PieceRun(SITE, going_in, (Changed("t", json.dumps(s)),)))

    runs = tuple(long_run(number) for number in range(1, 601))
    assert sum(len(each.run.changed[0].value) for each in runs) > model_runs.ANSWER_CAPACITY

    assert checked("def summary(s, t):\n    return {'t': t + s}", runs) is None


@pytest.mark.parametrize("seconds_left", [None, 60.0])
def test_a_formula_that_does_not_finish_within_the_check_s_limit_fails_the_check(
    seconds_left: float | None,
) -> None:
    until = None if seconds_left is None else time.monotonic() + seconds_left

    reason = checked("def summary(s, t):\n    return {'t': math.factorial(10 ** 7)}", until=until)

    assert isinstance(reason, str)
    assert reason.startswith("it did not finish on the past runs: ")


@pytest.mark.parametrize(
    "value",
    [
        # big-int arithmetic, which looks for signals, so the child's alarm ends it
        "math.factorial(10 ** 7)",
        # a sort, which does not, of values each slow to compare, so pyct's kill ends it
        "len(sorted([10 ** 90000 + 1, 10 ** 90000] * 10 ** 6))",
    ],
)
def test_a_check_the_run_s_deadline_ends_is_no_failed_formula(value: str) -> None:
    until = time.monotonic() + 0.2

    ended = checked(f"def summary(s, t):\n    return {{'t': {value}}}", until=until)

    assert ended == Ended("the run's budget ran out")


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
