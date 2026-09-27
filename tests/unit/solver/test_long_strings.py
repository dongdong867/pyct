"""A string answer: held to the most characters an answer holds, and written by cvc5 in full up
to there; decision answers-hold-at-most-a-million-items."""

import json
import logging
import shutil
from pathlib import Path

import pytest

from pyct.binding.bind import Seed
from pyct.binding.model import apply
from pyct.core.branch import Branch, Expression
from pyct.solver.answer import Sat, Unknown, Unsat
from pyct.solver.answer_size import MOST_ITEMS, longest_string
from pyct.solver.cvc5 import solve
from tests.unit.solver.test_cvc5 import NOT_UNKNOWN, ask, fake_cvc5, fork
from tests.unit.solver.test_render import render

needs_cvc5 = pytest.mark.skipif(shutil.which("cvc5") is None, reason="cvc5 is not installed")

# cvc5 1.3.4's form for a string longer than its default model length, 65,536 characters: a
# length and a counter, which name no one string
WITNESS = (
    "((arg.x (str.++ (witness ((@var.witness String)) (! (= (str.len @var.witness) 70000)"
    ' :witness (98 sort_to_term(String) 70000 0))) "z")))'
)


def test_a_string_leaf_is_held_to_the_most_characters_an_answer_holds() -> None:
    text = render((fork(["==", "s", "t"], taken=True),), {"s": str, "t": str, "n": int})

    # held right after the leaves are declared, before any fork
    assert text.splitlines()[1:5] == [
        "(declare-const |arg.s| String)",
        "(declare-const |arg.t| String)",
        "(assert (<= (str.len |arg.s|) 1000000))",
        "(assert (<= (str.len |arg.t|) 1000000))",
    ]


@pytest.mark.parametrize(
    "access",
    [
        pytest.param(["[]", "items", 0], id="in a list"),
        pytest.param(["[]", "config", "'name'"], id="in a dict"),
    ],
)
def test_a_string_inside_an_argument_is_held_to_the_most_characters(access: Expression) -> None:
    text = render((fork(["==", access, "'x'"], taken=True),), {json.dumps(access): str})

    assert "(declare-const |leaf.0| String)" in text.splitlines()
    assert longest_string("|leaf.0|") in text.splitlines()


def test_a_leaf_of_another_type_is_not_held_to_a_length() -> None:
    text = render((fork(["<", "n", 10], taken=True),), {"n": int})

    assert "str.len" not in text


def test_cvc5_is_asked_to_write_a_string_answer_in_full_up_to_the_most(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, out="unsat\n")

    ask(tmp_path, monkeypatch)

    assert "--strings-model-max-len=1000000" in (tmp_path / "argv").read_text().split()


def test_a_value_line_pyct_cannot_read_is_unknown_and_warned_about_with_the_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    fake_cvc5(tmp_path, out=f"sat\n{WITNESS}\n{NOT_UNKNOWN}")

    with caplog.at_level(logging.WARNING, logger="pyct.solver.cvc5"):
        assert ask(tmp_path, monkeypatch) == Unknown()

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, caplog.text
    assert WITNESS in warnings[0].getMessage()


@needs_cvc5
def test_the_real_cvc5_hands_back_a_string_past_its_default_model_length() -> None:
    answer = solve((fork(["==", ["[:]", "s", 70000, None], "'z'"], taken=True),), {"s": str}, 10.0)

    assert isinstance(answer, Sat), answer
    value = answer.model["s"]
    assert isinstance(value, str)
    assert len(value) == 70_001 and value.endswith("z")


@needs_cvc5
def test_the_real_cvc5_hands_back_a_string_of_the_most_characters() -> None:
    path = (fork(["==", ["[:]", "s", MOST_ITEMS - 1, None], "'z'"], taken=True),)

    answer = solve(path, {"s": str}, 10.0)

    assert isinstance(answer, Sat), answer
    value = answer.model["s"]
    assert isinstance(value, str)
    assert len(value) == MOST_ITEMS and value.endswith("z")


@needs_cvc5
def test_a_fork_only_a_longer_string_takes_is_unsat() -> None:
    path = (fork(["!=", ["[:]", "s", MOST_ITEMS, None], "''"], taken=True),)

    assert solve(path, {"s": str}, 10.0) == Unsat()


def _item_longer_than(least: int) -> tuple[Seed, tuple[Branch, ...]]:
    """A list of strs, read at 0, and a fork that the item is longer than ``least``."""
    seed = Seed.of({"items": ["a"]})
    item: Expression = ["[]", "items", 0]
    path = (
        fork([">", ["len", "items"], 0], taken=True),
        fork([">", ["len", item], least], taken=True),
    )
    return seed, path


@needs_cvc5
def test_a_fork_only_a_longer_string_item_of_a_list_takes_is_unsat() -> None:
    seed, path = _item_longer_than(1_500_000)

    assert solve(path, seed.leaves, 10.0, seed.lists, seed.values) == Unsat()


@needs_cvc5
def test_a_string_item_of_a_list_past_cvc5_s_default_model_length_is_handed_back() -> None:
    seed, path = _item_longer_than(100_000)

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    assert isinstance(answer, Sat), answer
    items = apply(seed, answer.model).args["items"]
    assert isinstance(items, list) and isinstance(items[0], str)
    assert MOST_ITEMS >= len(items[0]) > 100_000
