"""A split's list in SMT-LIB: how many pieces it holds, the piece at a position from either end,
and its count where a term reads it, with cvc5 held against Python on each."""

import random
import subprocess
import time

import pytest

from pyct.binding.bind import Seed
from pyct.binding.model import apply
from pyct.core.branch import Expression
from pyct.core.str_splits import LONGEST_WALK, overlaps_itself
from pyct.solver.answer import Sat, Unknown, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.list_reader import ProgramTooLargeError
from pyct.solver.list_terms import FALSE, TRUE, Lin, compare
from pyct.solver.lists import Origin
from pyct.solver.render import program
from pyct.solver.split_lists import SplitList
from pyct.solver.splits import named_classes
from pyct.solver.strings import encode
from tests.unit.solver.agreement import asked, needs_cvc5
from tests.unit.solver.test_render import fork, render

# the characters random strings are made of: separators, whitespace in and past ASCII, line
# breaks, and letters
LETTERS = [*"ab ,\t\n\r\x1c=", "\x85", "\u2028", "\u3000"]
SEPARATORS = [",", " ", "ab", "aa"]
COUNT = "count!0!"


def _form(rng: random.Random) -> tuple[str, tuple[object, ...]]:
    """A split pyct tracks: its head and plain operands, as core writes them."""
    head = rng.choice(["split", "rsplit", "splitlines"])
    if head == "splitlines":
        return head, rng.choice([(), (False,), (True,)])
    separator = rng.choice([None, *SEPARATORS])
    limit = rng.choice([-1, 0, 1, 2, LONGEST_WALK + 1])
    if head == "rsplit" and separator is not None and overlaps_itself(separator):
        # core hands an rsplit on a separator that overlaps itself on only when it is walked
        limit = rng.randint(0, 2)
    return head, rng.choice([(separator,), (separator, limit)]) if limit >= 0 else (separator,)


def _pieces(value: str, head: str, operands: tuple[object, ...]) -> list[str]:
    return getattr(value, head)(*operands)


def _program(asks: list[tuple[str, str, str]]) -> list[str]:
    """One program: each ask's string fixed, and the value of its term, in order."""
    lines = ["(set-logic ALL)"]
    for at, (value, sort, term) in enumerate(asks):
        lines += [f"(declare-const s{at} String)", f"(assert (= s{at} {encode(value)}))"]
        lines.append(f"(define-fun v{at} () {sort} {term.replace('|s|', f's{at}')})")
    lines[1:1] = named_classes("\n".join(lines))
    lines += ["(check-sat)", f"(get-value ({' '.join(f'v{at}' for at in range(len(asks)))}))"]
    return lines


def _listed(
    head: str, operands: tuple[object, ...], bound: int = 6, *, hold: bool = True
) -> SplitList:
    return SplitList("|s|", head, operands, COUNT, bound, [], hold)


@needs_cvc5
def test_cvc5_counts_the_pieces_of_every_split_as_python_does() -> None:
    rng = random.Random(3)
    asks: list[tuple[str, str, str]] = []
    expected: list[object] = []
    for _ in range(300):
        value = "".join(rng.choices(LETTERS, k=rng.randint(0, 7)))
        head, operands = _form(rng)
        listed, count = _listed(head, operands), len(_pieces(value, head, operands))
        for number in range(-1, 5):
            asks.append((value, "Bool", listed.past(number)))
            expected.append(count > number)

    assert asked(_program(asks)) == expected


@needs_cvc5
def test_cvc5_reads_each_piece_from_the_end_as_python_does() -> None:
    rng = random.Random(5)
    asks: list[tuple[str, str, str]] = []
    expected: list[object] = []
    for _ in range(200):
        value = "".join(rng.choices(LETTERS, k=rng.randint(0, 7)))
        head, operands = _form(rng)
        listed, pieces = _listed(head, operands, bound=9), _pieces(value, head, operands)
        back = rng.randint(0, 2)
        read = listed.read(Lin(-back - 1).plus(Lin.of(COUNT)), "str", {})
        there = back < len(pieces) and len(pieces) <= listed.bound + back
        if read.value is None:
            # a split whose limit leaves no piece that far from the end, on any string
            assert (read.guard, there) == (FALSE, False), (value, head, operands, back)
            continue
        asks.append((value, "Bool", read.guard))
        expected.append(there)
        if there:
            asks.append((value, "String", read.value))
            expected.append(pieces[-back - 1])

    assert asked(_program(asks)) == expected


@needs_cvc5
@pytest.mark.parametrize("hold", [True, False], ids=["held", "loosened"])
def test_cvc5_ties_the_count_to_the_pieces_below_its_bound(hold: bool) -> None:
    rng = random.Random(7)
    for _ in range(40):
        value = "".join(rng.choices(LETTERS, k=rng.randint(0, 9)))
        head, operands = _form(rng)
        listed = _listed(head, operands, bound=3, hold=hold)
        count = len(_pieces(value, head, operands))
        answer = _count_answer(value, listed)
        # held, a string with more pieces than the bound is no answer; loosened, its count is
        # at the bound or past it, though not fixed; on whitespace the count is exact either way
        words = head in ("split", "rsplit") and (not operands or operands[0] is None)
        exact = count <= 3 or words
        if exact:
            assert answer.startswith(f"sat\n((v0 {count}))"), (value, head, operands, answer)
        elif hold:
            assert answer.startswith("unsat"), (value, head, operands, answer)
        else:
            assert answer.startswith("sat\n((v0 "), (value, head, operands, answer)
            assert int(answer.split()[-1].rstrip(")")) >= 3, (value, head, operands, answer)


def _count_answer(value: str, listed: SplitList) -> str:
    """What cvc5 says the count is on one fixed string, with the list's tie asserted."""
    lines = [
        "(set-logic ALL)",
        "(declare-const |s| String)",
        f"(assert (= |s| {encode(value)}))",
        f"(declare-const {COUNT} Int)",
        *listed.tie(),
        f"(define-fun v0 () Int {COUNT})",
    ]
    lines[1:1] = named_classes("\n".join(lines))
    return subprocess.run(
        ["cvc5", "--produce-models", "--lang", "smt", "--quiet"],
        input="\n".join([*lines, "(check-sat)", "(get-value (v0))"]) + "\n",
        capture_output=True,
        text=True,
        check=False,
    ).stdout


@needs_cvc5
def test_cvc5_reads_a_piece_at_a_position_a_term_writes_as_python_does() -> None:
    rng = random.Random(11)
    asks: list[tuple[str, str, str]] = []
    expected: list[object] = []
    for _ in range(100):
        value = "".join(rng.choices(LETTERS, k=rng.randint(1, 7)))
        head, operands = _form(rng)
        pieces = _pieces(value, head, operands)
        if not pieces:
            continue
        at = rng.randrange(len(pieces))
        read = _listed(head, operands, bound=8).read(Lin.of(f"(+ 0 {at})"), "str", {})
        assert read.value is not None
        asks += [(value, "Bool", read.guard), (value, "String", read.value)]
        expected += [True, pieces[at]]

    assert asked(_program(asks)) == expected


def test_a_walked_rsplit_asserts_it_has_the_split_s_count_and_no_other_split_does() -> None:
    assert _listed("rsplit", (",", 2)).fact() != TRUE
    assert _listed("rsplit", (",",)).fact() == TRUE
    assert _listed("rsplit", (",", LONGEST_WALK + 1)).fact() == TRUE
    assert _listed("split", (",", 2)).fact() == TRUE


@needs_cvc5
def test_cvc5_holds_a_walked_rsplit_s_count_on_every_string() -> None:
    rng = random.Random(13)
    asks = []
    for _ in range(100):
        value = "".join(rng.choices(LETTERS, k=rng.randint(0, 8)))
        separator = rng.choice([None, *SEPARATORS])
        asks.append((value, "Bool", _listed("rsplit", (separator, rng.randint(0, 3))).fact()))

    assert asked(_program(asks)) == [True] * len(asks)


def test_the_loosened_program_reads_no_piece_among_those_below_the_bound() -> None:
    listed = _listed("splitlines", (), hold=False)

    with pytest.raises(ProgramTooLargeError):
        listed.read(Lin(-1).plus(Lin.of(COUNT)), "str", {})


def test_a_piece_of_another_kind_is_not_read() -> None:
    read = _listed("split", (",",)).read(Lin(0), "int", {})

    assert (read.value, read.guard) == (None, FALSE)


# a compare of a count with a number: the difference, whether it may be 0, and the count asked
BY_COUNT: dict[str, tuple[Lin, Lin, bool, str]] = {
    "count > 2": (Lin(2), Lin.of("c"), False, "P2"),
    "count >= 2": (Lin(2), Lin.of("c"), True, "P1"),
    "count + 1 > 3": (Lin(3), Lin.of("c").plus(Lin(1)), False, "P2"),
    "count < 3": (Lin.of("c"), Lin(3), False, "(not P2)"),
    "count <= 3": (Lin.of("c"), Lin(3), True, "(not P3)"),
    "count > -1": (Lin(-1), Lin.of("c"), False, "true"),
    "count < 0": (Lin.of("c"), Lin(0), False, "false"),
}


@pytest.mark.parametrize(
    ("low", "high", "or_equal", "written"), BY_COUNT.values(), ids=list(BY_COUNT)
)
def test_a_compare_of_a_count_with_a_number_is_whether_a_piece_is_there(
    low: Lin, high: Lin, or_equal: bool, written: str
) -> None:
    counts = {"c": lambda number: TRUE if number < 0 else f"P{number}"}

    assert compare(low, high, {}, or_equal=or_equal, counts=counts) == written


def test_a_compare_of_two_counts_is_written_as_it_is() -> None:
    counts = {"c": lambda number: f"P{number}", "d": lambda number: f"Q{number}"}

    assert compare(Lin.of("c"), Lin.of("d"), {}, counts=counts) == "(< c d)"


# a path whose fork names a split's length with a number, and one that meets a tracked int
SPLIT: Expression = ["split", "s", "','"]


def test_a_count_a_compare_with_a_number_reads_is_not_declared() -> None:
    text = render((fork(["==", ["len", SPLIT], 4], taken=True),), {"s": str})

    assert "count!" not in text


def test_a_count_that_meets_a_tracked_int_is_declared_and_tied_to_its_pieces() -> None:
    text = render((fork(["==", ["len", SPLIT], "n"], taken=True),), {"s": str, "n": int})

    assert "(declare-const count!0! Int)" in text
    assert "(assert (= count!0! " in text


@needs_cvc5
def test_an_item_of_a_list_after_a_split_s_list_is_read_where_the_answer_s_pieces_end() -> None:
    joined: Expression = ["+", SPLIT, "items"]
    path = (
        fork([">", ["len", joined], 2], taken=True),
        fork(["==", ["[]", joined, 2], "'z'"], taken=True),
        fork(["==", ["len", SPLIT], 2], taken=True),
    )
    seed = Seed.of({"s": "a", "items": ["x", "y"]})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    assert isinstance(answer, Sat), answer
    args = dict(apply(seed, answer.model).args)
    s, items = args["s"], args["items"]
    assert isinstance(s, str) and isinstance(items, list)
    assert [*s.split(","), *items][2] == "z" and len(s.split(",")) == 2, args


@needs_cvc5
def test_a_piece_read_beside_a_spelled_string_is_named_apart_from_its_letters() -> None:
    # the letters of a string read at fixed positions and the pieces a list read defines each
    # get a name of their own
    piece: Expression = ["[]", SPLIT, 0]
    letters = [fork(["==", ["[]", piece, at], "'a'"], taken=True) for at in range(4)]
    path = (fork([">", ["len", SPLIT], 0], taken=True), *letters)
    seed = Seed.of({"s": "aaaa,b"})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    assert isinstance(answer, Sat), answer


def test_a_read_from_the_end_of_many_lines_writes_a_program_of_bounded_size() -> None:
    # the input's own count is held to the cap, so a program over many lines stays small
    lines: Expression = ["splitlines", "s"]
    path = (
        fork([">=", ["len", lines], 1], taken=True),
        fork(["==", ["[]", lines, -1], "'z'"], taken=True),
    )
    origin = Origin(values={"s": "a\n" * 300})

    text = program(path, {"s": str}, origin).text

    assert len(text) < 2_000_000, len(text)


@needs_cvc5
@pytest.mark.parametrize(
    ("parts", "seed"),
    [(["split", "s", "','"], "a"), (["split", ["strip", "s"], "','"], "a")],
    ids=["the input's string", "a changed string"],
)
def test_a_path_past_the_bound_is_a_miss_that_says_so_never_unsat(
    parts: Expression, seed: str
) -> None:
    path = (
        fork(["==", ["len", parts], "n"], taken=True),
        fork(["==", "n", 40], taken=True),
    )
    args = Seed.of({"s": seed, "n": 0})

    answer = solve(path, args.leaves, 10.0, args.lists, args.values)

    # Python takes this path with 40 pieces, past the bound of 3: the held ask is unsat, and
    # the loosened one, which has an answer, says the fork is unknown
    assert isinstance(answer, Unknown), answer


@needs_cvc5
def test_a_path_that_needs_no_more_pieces_than_the_bound_is_answered_held() -> None:
    parts: Expression = ["split", "s", "','"]
    path = (
        fork(["<", ["len", parts], 36], taken=False),
        fork(["==", ["len", parts], "n"], taken=True),
    )
    args = Seed.of({"s": "a", "n": 0})

    answer = solve(path, args.leaves, 10.0, args.lists, args.values)

    # a split of the input's own string: 36 pieces is the cap, and 37 past it
    assert not isinstance(answer, Unsat), answer


@needs_cvc5
@pytest.mark.parametrize(
    "other",
    ["n", ["len", ["split", "t"]]],
    ids=["a tracked int", "another split's count"],
)
def test_a_whitespace_count_that_meets_a_term_is_answered_at_once(other: Expression) -> None:
    words: Expression = ["split", "s"]
    path = (fork(["==", ["len", words], other], taken=True), fork([">", "n", 2], taken=True))
    seed = Seed.of({"s": "a", "t": "b c", "n": 0})

    started = time.perf_counter()
    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    assert isinstance(answer, Sat), answer
    assert time.perf_counter() - started < 3.0
    args = dict(apply(seed, answer.model).args)
    s, t, n = str(args["s"]), str(args["t"]), args["n"]
    counted = n if other == "n" else len(t.split())
    assert len(s.split()) == counted and isinstance(n, int) and n > 2, args


@needs_cvc5
def test_an_unrelated_number_on_the_path_leaves_a_tie_small() -> None:
    split: Expression = ["split", "s", "','"]
    path = (
        fork([">", "x", 1000], taken=True),
        fork(["==", ["len", split], ["+", "m", 1]], taken=True),
    )
    seed = Seed.of({"s": "a", "x": 0, "m": 5})

    started = time.perf_counter()
    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    assert isinstance(answer, Sat), answer
    assert time.perf_counter() - started < 3.0
    args = dict(apply(seed, answer.model).args)
    s, x, m = str(args["s"]), args["x"], args["m"]
    assert isinstance(x, int) and isinstance(m, int), args
    assert x > 1000 and len(s.split(",")) == m + 1, args


@needs_cvc5
@pytest.mark.parametrize(
    "guard",
    [["<", ["len", "s"], 100], [">", ["len", ["split", "t", "','"]], 1000]],
    ids=["a string's length", "a large count of another split"],
)
def test_a_length_guard_leaves_a_split_s_flip_quick(guard: list[Expression]) -> None:
    split: Expression = ["split", "s", "','"]
    path = (
        fork(guard, taken=guard[0] == "<"),
        fork(["==", ["len", split], ["+", "m", 1]], taken=True),
        fork(["==", ["[]", split, 0], "'x'"], taken=True),
    )
    seed = Seed.of({"s": "a", "t": "b", "m": 5})

    started = time.perf_counter()
    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # a string's length says nothing of the pieces, and a count past 1,000 is one membership
    assert isinstance(answer, Sat), answer
    assert time.perf_counter() - started < 3.0
    args = dict(apply(seed, answer.model).args)
    s, t, m = str(args["s"]), str(args["t"]), args["m"]
    assert isinstance(m, int) and len(s.split(",")) == m + 1 and s.split(",")[0] == "x", args
    assert len(s) < 100 if guard[0] == "<" else len(t.split(",")) <= 1000, args


@needs_cvc5
def test_the_last_of_many_lines_is_read_where_the_input_s_count_puts_it() -> None:
    lines: Expression = ["splitlines", "s"]
    path = (
        fork([">=", ["len", lines], 1], taken=True),
        fork(["==", ["[]", lines, -1], "'z'"], taken=True),
    )
    seed = Seed.of({"s": "a\n" * 12})

    started = time.perf_counter()
    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # chosen among every count up to 14 this ran past the limit; read where the input's own
    # twelve lines put it, it answers at once
    assert isinstance(answer, Sat), answer
    assert time.perf_counter() - started < 8.0
    assert str(apply(seed, answer.model).args["s"]).splitlines()[-1] == "z"


@needs_cvc5
def test_an_rsplit_past_the_walk_counts_its_pieces_on_any_string() -> None:
    parts: Expression = ["rsplit", "s", "','", LONGEST_WALK + 1]
    path = (
        fork([">", ["len", parts], 2], taken=False),
        fork(["in", "',,,'", "s"], taken=True),
    )
    seed = Seed.of({"s": "a"})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # three commas make four pieces, so no string takes both; the string the pieces are read
    # on is the reads' restriction, not the count's, and does not free it
    assert isinstance(answer, Unsat), answer
