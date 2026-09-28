"""Made-up int keys of a `dict[int, X]`, written for cvc5 and read back: the smallest
non-negative ints the dict does not hold and no fork names."""

from pyct.binding.annotations import Items
from pyct.binding.bind import Seed
from pyct.solver.answer import Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.dict_keys import made_up_int_match
from tests.unit.solver.agreement import needs_cvc5
from tests.unit.solver.test_render_dicts import answered, fork

INT_KEYS = {"config": Items(dict, int, int)}


def test_a_made_up_int_skips_each_non_negative_int_taken() -> None:
    text = made_up_int_match("k", {3, 0, "1", -2}, "m")

    assert text == (
        "(and (>= k 0) (not (= k 0)) (not (= k 3)) "
        "(< (- k (+ 0 0 (ite (< 0 k) 1 0) (ite (< 3 k) 1 0))) m))"
    )


@needs_cvc5
def test_a_count_is_met_by_ints_the_dict_does_not_hold_and_no_fork_names() -> None:
    solved = answered(
        {"config": {"0": 5}},
        fork(["in", 1, "config"], taken=False),
        fork(["==", ["len", "config"], 3]),
        checks=INT_KEYS,  # pyrefly: ignore[bad-argument-type]
    )

    config = solved["config"]
    assert isinstance(config, dict) and list(config) == [0, 2, 3] and config[0] == 5


@needs_cvc5
def test_a_tracked_int_key_may_equal_a_made_up_int_key() -> None:
    solved = answered(
        {"n": 5, "config": {"0": 1}},
        fork(["in", "n", "config"]),
        fork(["!=", "n", 0]),
        fork([">", ["[]", "config", "n"], 5]),
        checks=INT_KEYS,  # pyrefly: ignore[bad-argument-type]
    )

    config, n = solved["config"], solved["n"]
    assert isinstance(config, dict) and isinstance(n, int) and n != 0
    assert list(config)[0] == 0 and config[n] > 5  # pyrefly: ignore[bad-index]


@needs_cvc5
def test_no_negative_int_key_is_made_up_for_a_tracked_key() -> None:
    seed = Seed.of({"n": 5, "config": {}}, INT_KEYS)  # pyrefly: ignore[bad-argument-type]
    forks = (fork(["in", "n", "config"]), fork(["<", "n", 0]))

    assert isinstance(solve(forks, seed.leaves, 10.0, seed.containers()), Unsat)
