"""Each list length and dict size the solver chooses is held small on the first ask, and grows
only where an unsat's core names its hold; a string keeps only its cap."""

import shutil
from pathlib import Path

import pytest

from pyct.binding.shapes import DictAnswer, DictShape, ListAnswer, ListShape
from pyct.core.branch import Branch, Expression
from pyct.solver.answer import Sat, Unsat
from pyct.solver.answer_size import MOST_ITEMS
from pyct.solver.cvc5 import solve
from tests.unit.solver.test_cvc5 import NOT_UNKNOWN, fork
from tests.unit.solver.test_cvc5_floats import asked, fake_cvc5

needs_cvc5 = pytest.mark.skipif(shutil.which("cvc5") is None, reason="cvc5 is not installed")

INTS = ListShape(("int",), fill="int")
EMPTY = ListShape((), fill="int")
ONE_KEY = DictShape(keys=("a",), kinds=("int",))


def length_of(answer: object, name: str) -> int:
    """The length a sat answer gives a list."""
    assert isinstance(answer, Sat), answer
    listed = answer.model[name]
    assert isinstance(listed, ListAnswer)
    return listed.length


def float_index(listed: Expression) -> tuple[Branch, ...]:
    """The forks `listed[int(f)] > 5` records on an index the seed's f has in range, the last
    flipped: f is finite, its int is inside the list, and the item there is not above 5."""
    at: Expression = ["int", "f"]
    return (
        fork(["isfinite", "f"], taken=True),
        fork([">", ["len", listed], at], taken=True),
        fork([">=", ["len", listed], ["-", at]], taken=True),
        fork([">", ["[]", listed, at], 5], taken=False),
    )


@needs_cvc5
def test_a_float_s_int_as_an_index_answers_a_short_list() -> None:
    # held only by its million-item cap, cvc5 1.3.4 answers a list of exactly that many
    answer = solve(float_index("ys"), {"f": float}, 5.0, {"ys": INTS}, {"f": 1.5})

    assert length_of(answer, "ys") <= 2 * 1 + 8


@needs_cvc5
def test_a_fork_only_a_long_list_takes_grows_its_hold_until_one_fits() -> None:
    answer = solve((fork([">", ["len", "xs"], 200], taken=True),), {}, 5.0, {"xs": EMPTY})

    # held to 8 items, then 128, then 2048
    assert 200 < length_of(answer, "xs") <= 8 * 16 * 16


@needs_cvc5
def test_a_fork_only_a_list_at_the_cap_takes_frees_the_hold() -> None:
    path = (fork([">", ["len", "xs"], MOST_ITEMS - 1], taken=True),)

    assert length_of(solve(path, {}, 5.0, {"xs": INTS}), "xs") == MOST_ITEMS


@needs_cvc5
def test_a_fork_past_the_cap_is_unsat_once_every_hold_is_free() -> None:
    path = (fork([">", ["len", "xs"], MOST_ITEMS], taken=True),)

    assert solve(path, {}, 5.0, {"xs": INTS}) == Unsat()


@needs_cvc5
def test_a_fork_only_a_large_dict_takes_grows_its_hold_until_one_fits() -> None:
    answer = solve((fork([">", ["len", "d"], 50], taken=True),), {}, 5.0, {"d": ONE_KEY})

    assert isinstance(answer, Sat)
    found = answer.model["d"]
    assert isinstance(found, DictAnswer)
    # held to 10 keys, then 160
    assert 50 < found.kept + found.made <= 10 * 16


def test_the_first_ask_holds_a_list_to_2n_and_8_and_a_string_to_its_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, f'sat\n((|arg.xs.len| 3))\n((|arg.s| "a"))\n{NOT_UNKNOWN}')
    monkeypatch.setenv("PATH", str(tmp_path))
    path = (fork([">", ["len", "xs"], 2], taken=True), fork(["==", "s", "'b'"], taken=False))

    solve(path, {"s": str}, 5.0, {"xs": ListShape(("int",) * 3, fill="int")}, {"s": "abcd"})

    [program] = asked(tmp_path)
    # a sat answer is the answer, so no core is asked for
    assert program[0] == "(set-logic ALL)"
    assert "(assert (<= |arg.xs.len| 14))" in program
    # the cap stays beside the hold
    assert f"(assert (<= 0 |arg.xs.len| {MOST_ITEMS}))" in program
    # a string keeps only its cap: held small, cvc5 can spend its whole limit proving that a
    # fork only a longer string takes is unsat
    assert [line for line in program if "str.len |arg.s|" in line] == [
        f"(assert (<= (str.len |arg.s|) {MOST_ITEMS}))"
    ]


def test_a_core_that_names_a_size_hold_grows_it_sixteen_fold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, "unsat\n", "unsat\n(\nsize!0\n)\n", "unsat\n", "unsat\n(\n)\n")
    monkeypatch.setenv("PATH", str(tmp_path))

    answer = solve((fork([">", ["len", "xs"], 5_000], taken=True),), {}, 5.0, {"xs": INTS})

    assert answer == Unsat()
    first, cored, grown, cored_again = asked(tmp_path)
    assert "(assert (<= |arg.xs.len| 10))" in first
    assert cored[0] == "(set-option :dump-unsat-cores true)"
    assert "(assert (! (<= |arg.xs.len| 10) :named size!0))" in cored
    assert "(assert (<= |arg.xs.len| 160))" in grown
    assert "(assert (! (<= |arg.xs.len| 160) :named size!0))" in cored_again


def test_an_unsat_whose_core_names_no_size_hold_is_the_path_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, "unsat\n", "unsat\n(\n)\n")
    monkeypatch.setenv("PATH", str(tmp_path))
    path = (fork(["==", ["len", "xs"], 1], taken=True), fork(["==", ["len", "xs"], 2], taken=True))

    assert solve(path, {}, 5.0, {"xs": INTS}) == Unsat()
    # one core ask is what an unsat that holds a size costs
    assert len(asked(tmp_path)) == 2


def test_a_hold_grown_to_the_cap_is_no_longer_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core = "unsat\n(\nsize!0\n)\n"
    # 10, 160, 2,560, 40,960, 655,360, and then past the cap
    fake_cvc5(tmp_path, *(["unsat\n", core] * 5), "unsat\n")
    monkeypatch.setenv("PATH", str(tmp_path))

    path = (fork([">", ["len", "xs"], MOST_ITEMS], taken=True),)
    assert solve(path, {}, 5.0, {"xs": INTS}) == Unsat()

    programs = asked(tmp_path)
    assert len(programs) == 11
    assert not any("(<= |arg.xs.len| " in line for line in programs[-1])


def test_a_path_that_names_no_size_asks_no_core(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, "unsat\n")
    monkeypatch.setenv("PATH", str(tmp_path))

    assert solve((fork(["<", "n", 3], taken=True),), {"n": int}, 5.0) == Unsat()
    assert len(asked(tmp_path)) == 1


@needs_cvc5
def test_an_unsat_on_ints_beside_a_held_list_is_unsat() -> None:
    path = (
        fork(["==", ["len", "xs"], 1], taken=True),
        fork([">", "n", 3], taken=True),
        fork(["<", "n", 2], taken=True),
    )

    assert solve(path, {"n": int}, 5.0, {"xs": INTS}) == Unsat()


@needs_cvc5
def test_an_unsat_on_a_dict_beside_its_hold_is_unsat() -> None:
    path = (fork([">", ["len", "d"], 3], taken=True), fork(["<", ["len", "d"], 2], taken=True))

    assert solve(path, {}, 5.0, {"d": ONE_KEY}) == Unsat()
