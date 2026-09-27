"""A path's conditions share their parts as Python holds them, and the program writes each once."""

import json
import random
import time

from pyct.core.branch import Branch, Expression
from pyct.solver.answer import Answer, Sat
from pyct.solver.cvc5 import solve
from pyct.solver.joined import joined
from pyct.solver.strings import below, sliced
from tests.unit.solver.agreement import (
    PATH_LETTERS,
    SITE,
    flipped_path,
    needs_cvc5,
    python,
    takes,
)
from tests.unit.solver.test_render import render
from tests.unit.solver.test_string_pieces import PYTHON_HEADS, UNFORKED_HEADS, piece_of

# the constants the program declares for the parameters s and x
S, X = "|arg.s|", "|arg.x|"

# the letters the character-edit loop's string is compared with at the end
LETTERS = "abcdefghijklmnopqrstuvwxyz" * 2


def fork(expression: Expression, *, taken: bool) -> Branch:
    return Branch(expression=expression, taken=taken, site=SITE)


def _edit_loop(passes: int, s: str) -> tuple[Branch, ...]:
    """`s = s[:i] + s[i] + s[i+1:]` for each i, then `s == 'abc…'`, as s takes it.

    Each pass holds the last pass's string three times, so written out the
    condition triples with every pass. The string is compared with at least
    as many letters as there are passes, so a string long enough for every
    pass can equal it. The last fork is flipped.
    """
    term: Expression = "s"
    forks: list[Branch] = []
    for i in range(passes):
        forks.append(fork([">", ["len", term], i], taken=True))
        term = ["+", ["+", ["[:]", term, None, i], ["[]", term, i]], ["[:]", term, i + 1, None]]
    last: Expression = ["==", term, repr(LETTERS[: max(passes, 18)])]
    return (*forks, fork(last, taken=not python(last, s, PYTHON_HEADS)))


def test_a_part_held_twice_is_defined_once() -> None:
    part: Expression = ["[:]", "s", 1, None]

    text = render((fork(["==", ["+", part, part], "'bcbc'"], taken=True),), {"s": str})

    assert f"(define-fun e!0 () String {sliced(S, 1, None)})" in text.splitlines()
    assert '(assert (= (str.++ e!0 e!0) "bcbc"))' in text.splitlines()


def test_a_part_two_forks_hold_is_defined_before_either() -> None:
    part: Expression = ["+", "s", "'x'"]

    text = render(
        (fork(["==", part, "'ax'"], taken=False), fork(["!=", part, "'bx'"], taken=True)),
        {"s": str},
    ).splitlines()

    assert text.index(f'(define-fun e!0 () String (str.++ {S} "x"))') < text.index(
        '(assert (not (= e!0 "ax")))'
    )
    assert '(assert (distinct e!0 "bx"))' in text


def test_a_part_a_form_reads_is_named_though_held_once() -> None:
    # an order against a literal reads its string once for each letter
    text = render((fork(["<", ["[:]", "s", 1, 3], "'mn'"], taken=True),), {"s": str})

    assert f"(define-fun e!0 () String {sliced(S, 1, 3)})" in text.splitlines()
    assert f"(assert {below('e!0', 'mn', or_equal=False)})" in text.splitlines()


def _asserted(expression: Expression, leaves: dict[str, type]) -> str:
    """The one assertion a one-fork program holds."""
    text = render((fork(expression, taken=True),), leaves)
    return next(line for line in text.splitlines() if line.startswith("(assert "))


# two pieces of one string side by side, and the one piece they are written as
JOINS: dict[str, tuple[Expression, str]] = {
    "s[:2] + s[2:]": (["+", ["[:]", "s", None, 2], ["[:]", "s", 2, None]], S),
    "s[:1] + s[1]": (["+", ["[:]", "s", None, 1], ["[]", "s", 1]], sliced(S, None, 2)),
    "s[1:3] + s[3:5]": (["+", ["[:]", "s", 1, 3], ["[:]", "s", 3, 5]], sliced(S, 1, 5)),
}


def test_two_pieces_of_one_string_side_by_side_are_written_as_the_one_they_make() -> None:
    for expression, written in JOINS.values():
        assert _asserted(["==", expression, "'abc'"], {"s": str}) == f'(assert (= {written} "abc"))'


def test_the_edit_loop_hands_the_solver_the_string_it_started_from() -> None:
    text = render(_edit_loop(18, "a" * 18), {"s": str}).splitlines()

    # every pass takes s apart and puts it back, so each fork reads s itself
    assert f'(assert (= {S} "abcdefghijklmnopqr"))' in text
    assert f"(assert (> (str.len {S}) 17))" in text
    assert not any(line.startswith("(define-fun") for line in text)


# pieces that do not make one piece: a gap, a bound counted from the end, two strings, two
# pieces out of order, a second piece that stops before it starts, and a first piece that starts
# past its stop
UNJOINED: dict[str, Expression] = {
    "s[:1] + s[2:]": ["+", ["[:]", "s", None, 1], ["[:]", "s", 2, None]],
    "s[:-1] + s[-1]": ["+", ["[:]", "s", None, -1], ["[]", "s", -1]],
    "s[:1] + t[1:]": ["+", ["[:]", "s", None, 1], ["[:]", "t", 1, None]],
    "s[2:] + s[:2]": ["+", ["[:]", "s", 2, None], ["[:]", "s", None, 2]],
    "s[:3] + s[3:2]": ["+", ["[:]", "s", None, 3], ["[:]", "s", 3, 2]],
    "s[3:1] + s[1:4]": ["+", ["[:]", "s", 3, 1], ["[:]", "s", 1, 4]],
}


def test_pieces_that_make_no_one_piece_are_joined_as_they_stand() -> None:
    for expression in UNJOINED.values():
        assert _asserted(["==", expression, "'abc'"], {"s": str, "t": str}).startswith(
            "(assert (= (str.++ "
        )


# the bounds the grid below takes pieces of s at: missing, from the start, from the end, and a
# bool, which Python takes as an int
BOUNDS: tuple[int | None, ...] = (None, 0, 1, 2, 3, 5, -1, -2, True)

# the strings each join in the grid is checked on, from empty to longer than any bound reaches
GRID_STRINGS = ("", "a", "ab", "abc", "abcd", "abcdefg")


def _pieces() -> list[Expression]:
    """Every slice of s between two of the bounds, and every index of s at one."""
    slices: list[Expression] = [["[:]", "s", start, stop] for start in BOUNDS for stop in BOUNDS]
    indexes: list[Expression] = [["[]", "s", index] for index in BOUNDS if index is not None]
    return slices + indexes


def _written(pair: Expression) -> Expression:
    """Two pieces side by side as the program writes them: the one piece they make, if any."""
    (written,) = joined((fork(["==", pair, "''"], taken=True),), lambda _: False)
    assert isinstance(written.expression, list)
    return written.expression[1]


def _value(expression: Expression, s: str) -> object:
    """What Python makes of pieces of s, or None where an index is past the end and raises."""
    try:
        return python(expression, s, PYTHON_HEADS)
    except IndexError:
        return None


def test_a_join_means_in_python_what_its_two_pieces_meant() -> None:
    pairs: list[Expression] = [["+", left, right] for left in _pieces() for right in _pieces()]
    joins = [(pair, whole) for pair in pairs if (whole := _written(pair)) is not pair]

    # a raise stops the target before it joins the pieces, so only a join Python makes counts
    wrong = [
        (pair, whole, s)
        for pair, whole in joins
        for s in GRID_STRINGS
        if (value := _value(pair, s)) is not None and _value(whole, s) != value
    ]

    assert len(joins) > 100
    assert wrong == []


# two strings inside a list, the leaves binding names by their accesses
ITEMS: dict[str, type] = {
    json.dumps(["[]", "items", 0]): str,
    json.dumps(["[]", "items", 1]): str,
}


def test_two_strings_inside_a_list_are_joined_as_two_values() -> None:
    first: Expression = ["[]", "items", 0]
    second: Expression = ["[]", "items", 1]

    # each is a value the seed holds, not a piece of the list, so nothing makes them one piece
    assert _asserted(["==", ["+", first, second], "'ab'"], ITEMS) == (
        '(assert (= (str.++ |leaf.0| |leaf.1|) "ab"))'
    )


def test_two_pieces_of_a_string_inside_a_list_are_the_string() -> None:
    string: Expression = ["[]", "items", 0]
    pieces: Expression = ["+", ["[:]", string, None, 1], ["[:]", string, 1, None]]

    assert _asserted(["==", pieces, "'ab'"], ITEMS) == '(assert (= |leaf.0| "ab"))'


def test_a_sum_of_two_operations_on_ints_is_added_as_it_stands() -> None:
    expression: Expression = ["==", ["+", ["-", "x", 1], ["-", "x", 2]], 5]

    assert _asserted(expression, {"x": int}) == f"(assert (= (+ (- {X} 1) (- {X} 2)) 5))"


def test_a_fork_on_a_bare_truth_value_holds_no_part() -> None:
    text = render((fork(True, taken=False),), {})

    assert text.splitlines() == ["(set-logic ALL)", "(assert (not true))", "(check-sat)"]


def test_a_sum_built_over_five_thousand_passes_is_written_out() -> None:
    term: Expression = "x"
    for _ in range(5000):
        term = ["+", term, 1]

    # nested far past Python's recursion limit, and held once, so written out where it stands
    assert _asserted(["==", term, 5], {"x": int}) == (
        f"(assert (= {'(+ ' * 5000}{X}{' 1)' * 5000} 5))"
    )


def test_a_string_built_over_five_thousand_passes_is_defined_once() -> None:
    term: Expression = "s"
    for _ in range(5000):
        term = ["+", term, "' '"]

    text = render((fork(["startswith", term, "'ok'"], taken=True),), {"s": str}).splitlines()

    # a form reads the string, so it is defined, written out once down to s
    opened, closed = "(str.++ ", ' " ")'
    assert f"(define-fun e!0 () String {opened * 5000}{S}{closed * 5000})" in text


def _marked_loop(passes: int) -> tuple[Branch, ...]:
    """`s = s[:i] + "x" + s[i+1:]` for each i, then `s != ''`: two pieces with a mark between.

    Nothing joins, so each pass holds the last pass's string twice, and
    written out the condition doubles with every pass.
    """
    term: Expression = "s"
    for i in range(passes):
        term = ["+", ["+", ["[:]", term, None, i], "'x'"], ["[:]", term, i + 1, None]]
    return (fork(["!=", term, "''"], taken=True),)


def test_the_character_edit_loop_grows_the_program_by_one_pass_at_a_time() -> None:
    edits = {
        passes: len(render(_edit_loop(passes, "a" * passes), {"s": str})) for passes in (18, 30)
    }
    marks = {passes: len(render(_marked_loop(passes), {"s": str})) for passes in (18, 30)}

    # each pass defines its string once, or joins it back into s, and adds its own fork; written
    # out, thirty passes would hold about 3 ** 30 and 2 ** 30 copies of s
    assert edits[30] - edits[18] < 12 * 200
    assert marks[30] - marks[18] < 12 * 200
    assert (edits[18], marks[18]) < (18 * 200, 18 * 200)


def _unshared(expression: Expression) -> Expression:
    """The same condition with no part shared: every list its own copy."""
    if not isinstance(expression, list):
        return expression
    return [_unshared(part) for part in expression]


def _answered_alike(path: tuple[Branch, ...]) -> tuple[Answer, Answer]:
    """cvc5's answers to the path as Python shares it and as a tree written out."""
    unshared = tuple(
        Branch(expression=_unshared(branch.expression), taken=branch.taken, site=branch.site)
        for branch in path
    )
    return solve(path, {"s": str}, 5.0), solve(unshared, {"s": str}, 5.0)


def _shared_path(rng: random.Random) -> tuple[Branch, ...]:
    """Random compares on pieces, each taken of a piece an earlier fork made, the last flipped."""
    s = "".join(rng.choices(PATH_LETTERS, k=rng.randint(0, 5)))
    pool: list[Expression] = ["s"]
    conditions: list[tuple[Expression, Expression | None]] = []
    for _ in range(rng.randint(1, 5)):
        term, long_enough = piece_of(rng, rng.choice(pool))
        if rng.random() < 0.3:
            term = ["+", term, piece_of(rng, rng.choice(pool), UNFORKED_HEADS)[0]]
        pool.append(term)
        literal = repr("".join(rng.choices(PATH_LETTERS, k=rng.randint(0, 3))))
        conditions.append(([rng.choice(["==", "!=", "<", ">="]), term, literal], long_enough))
    return flipped_path(s, conditions, PYTHON_HEADS)


@needs_cvc5
def test_cvc5_answers_a_shared_program_as_it_answers_the_program_written_out() -> None:
    rng = random.Random(2)
    paths = [_edit_loop(passes, "ab" * 3) for passes in range(1, 7)]
    paths += [_shared_path(rng) for _ in range(40)]

    answers = [_answered_alike(path) for path in paths]

    # sharing changes how the program is written, never what it says: the same answer each
    # time, and each model takes the path in Python
    assert [type(shared) for shared, _ in answers] == [type(tree) for _, tree in answers]
    models = [
        (path, answer)
        for path, pair in zip(paths, answers, strict=True)
        for answer in pair
        if isinstance(answer, Sat)
    ]
    assert models
    assert all(takes(path, str(answer.model["s"]), PYTHON_HEADS) for path, answer in models)


@needs_cvc5
def test_cvc5_flips_the_last_fork_of_the_character_edit_loop_thirty_passes_deep() -> None:
    path = _edit_loop(30, "a" * 30)

    start = time.perf_counter()
    answer = solve(path, {"s": str}, 10.0)
    spent = time.perf_counter() - start

    assert isinstance(answer, Sat), answer
    assert takes(path, str(answer.model["s"]), PYTHON_HEADS)
    assert spent < 5.0
