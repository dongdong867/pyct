"""A reply is read as one expression on the parameters, refused outside the form, and otherwise
compiled with its `and`, `or`, `not` and chained compares written on bools."""

import time
import types

import pytest

from pyct.intercept.model_code import Refused
from pyct.rewrite.condition import (
    FORM,
    FUNCTION,
    HELD_COL,
    HELD_LINE,
    MOST_CHARACTERS,
    MOST_DEPTH,
    expression_in,
    rewrite_code,
)
from pyct.run import model_runs
from pyct.run.model_runs import ModelCall, ModelRun, run_model

FILE = "<rewrite m:2:7>"
PARAMETERS = ("s", "n", "a")


@pytest.fixture(autouse=True)
def _one_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model_runs, "running", lambda: 1)


def refusal(expression: str) -> str:
    code = rewrite_code(expression, PARAMETERS, FILE)
    assert isinstance(code, Refused), expression
    return code.reason


def own_fork(expression: str, args: dict[str, object]) -> tuple[object, bool]:
    """The expression and side of the rewrite's own fork, run on ``args``."""
    code = rewrite_code(expression, PARAMETERS, FILE)
    assert isinstance(code, types.CodeType), code
    done = run_model(ModelCall(code, FUNCTION, args), time.monotonic() + 5)
    assert isinstance(done, ModelRun)
    [fork] = [
        fork
        for fork in done.result.branches
        if (fork.site.line, fork.site.col) == (HELD_LINE, HELD_COL)
    ]
    return fork.expression, fork.taken


@pytest.mark.parametrize(
    ("reply", "expression"),
    [
        ('s == "1e-30"', 's == "1e-30"'),
        ('  s == "1e-30"\n', 's == "1e-30"'),
        ("Here it is:\n```python\nn > 3\n```\n", "n > 3"),
        ("```\nn > 3\n```", "n > 3"),
    ],
)
def test_the_expression_is_the_fence_s_text_or_the_whole_reply(reply: str, expression: str) -> None:
    assert expression_in(reply, PARAMETERS) == expression


@pytest.mark.parametrize(
    "reply", ["", "   ", "this is not code", "x == 1", "n >", "n = 3", "len('ab') == 2"]
)
def test_a_reply_with_no_expression_on_the_parameters_holds_none(reply: str) -> None:
    assert expression_in(reply, PARAMETERS) is None


@pytest.mark.parametrize(
    ("expression", "reason"),
    [
        ("n == other", "a rewrite may not read other"),
        ('__import__("os").getcwd() == s', "a rewrite may not call __import__"),
        ("open(s) == n", "a rewrite may not call open"),
        ("s.__len__() == 1", "a rewrite may not call __len__"),
        ("s.real == 1", "a rewrite may not read the attribute real"),
        ("math.nothing(a) > 1", "math has no function nothing"),
        ("[c for c in s] == n", "a rewrite may not use a comprehension"),
        ("(lambda: n) == 1", "a rewrite may not use a lambda"),
        ("n if s else n", "a rewrite may not use an if expression"),
        ("(m := n) > 1", "a rewrite may not use an assignment"),
        ("len(*s) == 1", "a rewrite may not unpack arguments"),
        ("min(**s) == 1", "a rewrite may not unpack arguments"),
        ("s == b'x'", "a rewrite may not use that literal"),
        ("{s: n} == n", "a rewrite may not use Dict"),
        ('"{0.real}".format(n) == "1"', "a rewrite may not call format"),
        ('"{n}".format_map(s) == "1"', "a rewrite may not call format_map"),
        ("max(n, 1, key=s) == 1", "a rewrite may not pass a key function"),
    ],
)
def test_a_rewrite_outside_the_form_is_refused(expression: str, reason: str) -> None:
    assert refusal(expression) == reason


def test_a_rewrite_called_through_another_call_is_refused() -> None:
    assert refusal("min(n, 1)(n) == 1") == "a rewrite calls only a function by its name or a method"


def test_a_rewrite_too_long_or_too_deep_is_refused() -> None:
    assert refusal("n + " * MOST_CHARACTERS + "1 > 0").startswith("the rewrite is longer than")
    assert (
        refusal("-" * (MOST_DEPTH + 1) + "n > 0")
        == f"the rewrite nests more than {MOST_DEPTH} deep"
    )


def test_a_name_called_that_is_also_a_parameter_is_refused() -> None:
    code = rewrite_code("len(s) > 1", ("s", "len"), FILE)

    assert isinstance(code, Refused)
    assert code.reason == "a rewrite may not call len"


def test_and_or_and_not_are_one_fork_on_bools() -> None:
    expression, taken = own_fork("not s or n > 0 and n < 5", {"s": "x", "n": 3, "a": 1.0})

    assert expression == [
        "|",
        ["^", ["!=", "s", "''"], True],
        ["&", [">", "n", 0], ["<", "n", 5]],
    ]
    assert taken is True


def test_a_chained_compare_is_one_fork() -> None:
    expression, taken = own_fork("0 < n < 5", {"s": "x", "n": 9, "a": 1.0})

    assert expression == ["&", [">", "n", 0], ["<", "n", 5]]
    assert taken is False


def test_a_math_function_and_a_method_are_followed() -> None:
    assert own_fork("math.sqrt(a) > 512", {"s": "x", "n": 0, "a": 4.0})[0] == [
        ">",
        ["sqrt", "a"],
        512,
    ]
    assert own_fork('s.upper() == "X"', {"s": "x", "n": 0, "a": 4.0}) == (
        ["==", ["upper", "s"], "'X'"],
        True,
    )


def test_an_item_and_a_negation_of_a_number_are_followed() -> None:
    assert own_fork('s[0] == "x"', {"s": "xy", "n": 0, "a": 1.0}) == (
        ["==", ["[]", "s", 0], "'x'"],
        True,
    )
    assert own_fork("-n < 0", {"s": "x", "n": 2, "a": 1.0})[1] is True


def test_a_reply_over_several_lines_or_with_a_control_character_is_read_as_one_line() -> None:
    spread = expression_in("```python\n(n > 1\n and n < 3)\n```", PARAMETERS)
    marked = expression_in('s == "\x1b[31m"', PARAMETERS)

    assert spread == "n > 1 and n < 3"
    assert marked == "s == '\\x1b[31m'"


def test_the_form_says_every_operand_runs() -> None:
    assert "Each operand of and, or and not runs on every input" in FORM
