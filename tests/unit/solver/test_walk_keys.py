"""A dict's walk keys in a path: each ask writes them as the input's keys, and the ask with chosen
keys leaves the key at each pass a fork names to the solver (let-the-solver-choose-a-small-dict-
s-walk-key)."""

import time

import pytest

from pyct.binding.annotations import check_of
from pyct.binding.bind import Seed
from pyct.binding.model import apply
from pyct.binding.shapes import DictAnswer, DictShape, rekeyed
from pyct.core.branch import Branch, Expression, Fact, Site
from pyct.solver import cvc5, walk_keys
from pyct.solver.answer import Answer, Sat, Timeout, Unknown, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.walk_keys import Walks, leaf
from tests.unit.solver.agreement import needs_cvc5

SITE = Site("m.py", 2, 7)


@pytest.fixture(autouse=True)
def _a_run_of_its_own() -> None:
    """Each test asks as a run of its own does: no site has missed yet."""
    walk_keys.forget()


D: Expression = ["key", "d", 0]


def fork(expression: Expression, *, taken: bool = True) -> Branch:
    return Branch(expression=expression, taken=taken, site=SITE)


def fact(expression: Expression, place: Expression = None) -> Fact:
    return Fact(expression, True, SITE, place=place)


def walked(at: int) -> Fact:
    """The fact of the place a walk of `d` read its key at pass ``at``."""
    return fact(None, ["walked", "d", ["key", "d", at]])


def int_only(keys: int, value: int) -> tuple[Seed, tuple[Branch | Fact, ...]]:
    """`int_only`'s path from an N-key seed: pass 0 reads a value above 5, and the flip of the
    line-11 lookup of 1."""
    check = check_of(dict[int, int])
    assert check is not None
    seed = Seed.of({"d": {key: value for key in range(1, keys + 1)}}, {"d": check})
    path = (
        fork([">", ["len", "d"], 0]),
        walked(0),
        fact(["in", D, "d"]),
        fork([">", ["[]", "d", D], 5]),
        fork(["in", 1, "d"], taken=False),
    )
    return seed, path


def test_the_first_ask_writes_each_walk_key_as_the_input_s_key() -> None:
    shape = DictShape(keys=("a", "b"), kinds=("int", "int"))
    shared: Expression = ["[]", "d", ["key", "d", 1]]
    path = (fork([">", shared, 5]), fork(["<", shared, 9]), walked(1))

    written = Walks(path, {"d": shape}).fixed(path)

    assert [step.expression for step in written[:2]] == [
        [">", ["[]", "d", "'b'"], 5],
        ["<", ["[]", "d", "'b'"], 9],
    ]
    # a part the path shares is written once, and still shared
    assert written[0].expression[1] is written[1].expression[1]  # type: ignore[index]
    # a pass whose key a step names keeps it whatever a fork reads there
    assert written[2].place == ["given", ["walked", "d", "'b'"]]  # type: ignore[union-attr]


def test_a_path_with_no_walk_key_is_kept_as_it_is() -> None:
    path = (fork([">", "x", 5]),)

    assert Walks(path, {}).fixed(path) is path


def test_the_ask_with_chosen_keys_opens_each_pass_a_fork_names() -> None:
    shape = DictShape(keys=(1, 2, 3), kinds=("int",) * 3, int_keys=True)
    path = (
        walked(0),
        fact(["in", D, "d"]),
        walked(1),
        fork([">", ["[]", "d", ["key", "d", 2]], 5]),
        walked(2),
    )
    walks = Walks(path, {"d": shape})

    assert walks.chosen() == {("d", 2)}
    opened, leaves, values, orders = walks.opened(path)
    chosen = leaf(("d", 2))
    assert leaves == {chosen: int} and values == {chosen: 3}
    # every pass up to the last one a step names is held in order, the input's key where none
    # is chosen; the walks' places are left to the order
    assert orders == {"d": ((None, 1), (None, 2), (chosen, 3))}
    assert [step.expression for step in opened] == [
        ["in", 1, "d"],
        [">", ["[]", "d", chosen], 5],
    ]


def test_a_fact_that_keeps_a_walk_key_at_the_input_s_key_chooses_none() -> None:
    shape = DictShape(keys=("a",), kinds=("int",))
    path = (fact(["==", D, "'a'"]), fork([">", ["[]", "d", D], 5]))

    assert Walks(path, {"d": shape}).chosen() == set()


def test_a_dict_with_a_place_no_walk_key_names_chooses_none() -> None:
    shape = DictShape(keys=("a",), kinds=("int",))
    path = (fork([">", ["[]", "d", D], 5]), fact(None, ["last", "d", "'a'"]))

    assert Walks(path, {"d": shape}).chosen() == set()


def test_an_answer_lists_its_first_keys_before_the_rest() -> None:
    answer = DictAnswer(present={1: False}, kept=2, made=1, first=(0, 3))

    rebuilt = rekeyed({1: 9, 2: 9, 3: 9}, answer, DictShape((1, 2, 3), ("int",) * 3, "int", True))

    assert list(rebuilt) == [0, 3, 2]


@needs_cvc5
def test_an_unsat_with_the_input_s_keys_asks_with_them_chosen() -> None:
    seed, path = int_only(1, 9)

    answer = solve(path, seed.leaves, 10.0, seed.containers(), seed.values)

    assert isinstance(answer, Sat), answer
    d = apply(seed, answer.model).args["d"]
    assert isinstance(d, dict)
    first = next(iter(d))
    assert first != 1 and 1 not in d and d[first] > 5


@needs_cvc5
def test_a_sat_with_the_input_s_keys_is_the_answer() -> None:
    seed, path = int_only(2, 9)
    flipped = (*path[:3], fork([">", ["[]", "d", D], 5], taken=False))

    answer = solve(flipped, seed.leaves, 10.0, seed.containers(), seed.values)

    assert isinstance(answer, Sat), answer
    d = apply(seed, answer.model).args["d"]
    assert isinstance(d, dict) and list(d)[0] == 1 and d[1] <= 5


@needs_cvc5
def test_a_chosen_key_must_be_a_key_the_dict_may_hold() -> None:
    # the key a fork compares the walk key with is one a fork names, which the solver may add
    seed = Seed.of({"d": {"x": 9}})
    path = (fork([">", ["len", "d"], 0]), walked(0), fork(["==", D, "'admin'"]))

    answer = solve(path, seed.leaves, 10.0, seed.containers(), seed.values)

    assert isinstance(answer, Sat), answer
    assert list(apply(seed, answer.model).args["d"])[0] == "admin"  # type: ignore[call-overload]


@needs_cvc5
def test_chosen_keys_given_up_go_on_without_places(monkeypatch: pytest.MonkeyPatch) -> None:
    # past its lookup steps the ask with chosen keys is given up at once, and the ask without
    # places answers: a model there is `unknown`, never a timeout
    monkeypatch.setattr(cvc5, "LOOKUP_STEPS_PER_SECOND", 1)
    seed, path = int_only(1, 9)

    started = time.monotonic()
    answer = solve(path, seed.leaves, 10.0, seed.containers(), seed.values)

    assert isinstance(answer, Unknown) and time.monotonic() - started < 1.0
    for _ in range(walk_keys.MOST_MISSES):
        solve(path, seed.leaves, 10.0, seed.containers(), seed.values)
    # each give-up cost nothing, so the site still asks with chosen keys
    assert not walk_keys.given_up(path)


@needs_cvc5
def test_chosen_keys_past_their_second_go_on_without_places(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # an ask with chosen keys runs at most CHOSEN_SECONDS, and is then stopped
    monkeypatch.setattr(cvc5, "CHOSEN_SECONDS", 0.001)
    seed, path = int_only(200, 9)

    answer = solve(path, seed.leaves, 10.0, seed.containers(), seed.values)

    assert isinstance(answer, Unknown), answer


@needs_cvc5
def test_a_walked_dict_grows_past_the_cap() -> None:
    # `if len(d) > 250` after a walk: the first ask holds no cap, as before walk keys
    seed = Seed.of({"d": {"a": 1}})
    path = (fork([">", ["len", "d"], 0]), walked(0), fork([">", ["len", "d"], 250]))

    assert isinstance(solve(path, seed.leaves, 10.0, seed.containers(), seed.values), Sat)


def test_a_dict_past_the_cap_chooses_no_key() -> None:
    shape = DictShape(keys=tuple(range(201)), kinds=("int",) * 201, int_keys=True)
    path = (fork([">", ["[]", "d", D], 5]),)

    assert Walks(path, {"d": shape}).chosen() == set()


@needs_cvc5
def test_a_walk_key_that_names_no_input_key_is_unknown() -> None:
    seed = Seed.of({"d": {"a": 1}})
    path = (fork([">", ["[]", "d", ["key", "d", 3]], 5]),)

    assert isinstance(solve(path, seed.leaves, 10.0, seed.containers(), seed.values), Unknown)


@needs_cvc5
@pytest.mark.parametrize(
    "flipped",
    [["!=", D, D], ["==", ["lower", D], "'admin'"], ["startswith", D, "'x'"]],
    ids=["itself", "lowered", "a-prefix"],
)
def test_an_unsat_that_names_a_walk_key_is_unknown(flipped: Expression) -> None:
    # every ask held places or chose among listed keys only, so an unsat is not the path's
    seed = Seed.of({"d": {"a": 1}})
    path = (fork([">", ["len", "d"], 0]), walked(0), fork(flipped))

    assert isinstance(solve(path, seed.leaves, 10.0, seed.containers(), seed.values), Unknown)


@needs_cvc5
def test_an_unsat_no_walk_key_takes_part_in_stays_unsat() -> None:
    seed = Seed.of({"d": {"a": 1}, "x": 0})
    path = (fork([">", ["len", "d"], 0]), walked(0), fork(["!=", "x", "x"]))

    assert isinstance(solve(path, seed.leaves, 10.0, seed.containers(), seed.values), Unsat)


@needs_cvc5
def test_a_compared_walk_key_stays_in_its_place() -> None:
    # the dict probe's `any(key == "b" for key in d)` then `"b" in d`: the compare reads no
    # value, and an answer that drops "b" would walk another key at pass 2
    seed = Seed.of({"d": {"c": 0, "a": 0, "b": 0}})
    key: Expression = ["key", "d", 2]
    path = (
        fork([">", ["len", "d"], 2]),
        walked(2),
        fork(["==", key, "'b'"]),
        fork(["in", "'b'", "d"], taken=False),
    )

    answer = solve(path, seed.leaves, 10.0, seed.containers(), seed.values)

    assert isinstance(answer, Unsat | Unknown), answer


@needs_cvc5
def test_an_unsat_without_the_walk_key_steps_stays_unsat() -> None:
    # the walk's value fork names a walk key; `len(d) > 1` in a `dict[int, X]` holding a str
    # key, where no key is made up, is unsat on every walk, which the ask without the walk
    # key's steps says
    check = check_of(dict[int, int])
    assert check is not None
    seed = Seed.of({"d": {"a": 1}}, {"d": check})
    path = (
        fork([">", ["len", "d"], 0]),
        walked(0),
        fork([">", ["[]", "d", D], 10], taken=False),
        fork([">", ["len", "d"], 1]),
    )

    answer = solve(path, seed.leaves, 10.0, seed.containers(), seed.values)

    assert isinstance(answer, Unsat), answer


def test_a_path_where_a_walk_key_escaped_chooses_none() -> None:
    shape = DictShape(keys=("a", "b"), kinds=("int", "int"))
    key: Expression = ["key", "d", 1]
    path = (fact(["==", key, "'b'"]), fork([">", ["[]", "d", D], 5]))

    assert Walks(path, {"d": shape}).chosen() == set()


def test_a_dict_whose_walk_read_every_key_chooses_none() -> None:
    shape = DictShape(keys=("a",), kinds=("int",))
    path = (
        fork([">", ["len", "d"], 0]),
        fork([">", ["[]", "d", D], 5], taken=False),
        fork([">", ["len", "d"], 1], taken=False),
        fork([">", "x", 0]),
    )

    assert Walks(path, {"d": shape}).chosen() == set()


@needs_cvc5
def test_an_unsat_on_an_escaped_walk_key_is_unknown() -> None:
    # v2 recorded no fork there: an unsat holding the key the escape kept would claim too much
    seed = Seed.of({"d": {"a": 1}})
    path = (fork([">", ["len", "d"], 0]), walked(0), fact(["==", D, "'a'"]), fork(["==", D, "'b'"]))

    assert isinstance(solve(path, seed.leaves, 10.0, seed.containers(), seed.values), Unknown)


@needs_cvc5
def test_an_unsat_that_rests_on_an_escape_is_unknown() -> None:
    # `seen.add(k)` then `"a" not in d`: the escape keeps the walk key at "a", and the dict
    # holds the key its walk read, so with the escape the flip is unsat; {"b": 9} takes it
    seed = Seed.of({"d": {"a": 9}})
    path = (
        fork([">", ["len", "d"], 0]),
        walked(0),
        fact(["==", D, "'a'"]),
        fact(["in", D, "d"]),
        fork([">", ["[]", "d", D], 5]),
        fork(["in", "'a'", "d"], taken=False),
    )

    assert isinstance(solve(path, seed.leaves, 10.0, seed.containers(), seed.values), Unknown)


def test_a_site_that_keeps_missing_is_asked_with_the_input_s_keys() -> None:
    path = (fork([">", ["[]", "d", D], 5]),)

    for _ in range(walk_keys.MOST_MISSES):
        assert not walk_keys.given_up(path)
        walk_keys.missed(path)

    assert walk_keys.given_up(path)
    walk_keys.forget()
    assert not walk_keys.given_up(path)


@needs_cvc5
@pytest.mark.parametrize(
    ("answer", "gives_up"),
    [(Unknown(unasked=True), False), (Unknown(), True), (Unsat(), True), (Timeout(), True)],
)
def test_an_ask_with_chosen_keys_the_step_guard_gave_up_counts_no_miss(
    monkeypatch: pytest.MonkeyPatch, answer: Answer, gives_up: bool
) -> None:
    # the step guard gives an ask up before cvc5 runs, at no cost, so the site keeps asking
    # with chosen keys, where a later path may choose fewer; an ask cvc5 ran counts, whatever
    # it answered
    seed, path = int_only(1, 9)
    monkeypatch.setattr(cvc5, "_chosen", lambda *_: answer)

    for _ in range(walk_keys.MOST_MISSES):
        solve(path, seed.leaves, 10.0, seed.containers(), seed.values)

    assert walk_keys.given_up(path) is gives_up
