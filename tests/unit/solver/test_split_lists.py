"""A split's list in SMT-LIB: how many pieces it holds, the piece at a position from either end,
and its count where a term reads it, with cvc5 held against Python on each."""

import random

import pytest

from pyct.binding.bind import Seed
from pyct.binding.model import apply
from pyct.core.branch import Expression
from pyct.core.str_splits import LONGEST_WALK, overlaps_itself
from pyct.solver.answer import Sat, Unknown
from pyct.solver.cvc5 import solve
from pyct.solver.list_terms import FALSE, TRUE, Lin, compare
from pyct.solver.lists import Origin
from pyct.solver.render import program
from pyct.solver.split_lists import SplitList
from pyct.solver.split_paths import Splits
from pyct.solver.splits import named_classes, right_piece
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
    head: str, operands: tuple[object, ...], count: int | None = None, *, fixed: bool = True
) -> SplitList:
    """A split's list whose input had ``count`` pieces, which is also its c*."""
    return SplitList("|s|", head, operands, COUNT, count, count, fixed)


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
def test_cvc5_counts_many_separators_as_python_does() -> None:
    rng = random.Random(4)
    asks: list[tuple[str, str, str]] = []
    expected: list[object] = []
    for _ in range(80):
        separator = rng.choice([",", "aa", "ab"])
        # fifteen to twenty-two separators, with letters and commas among them
        fields = rng.choices(["", "a", "b", ",", "ba"], k=rng.randint(16, 23))
        value = separator.join(fields)
        head = rng.choice(["split", "rsplit"])
        limit = rng.choice([None, 15, 17, 18, 30])
        operands: tuple[object, ...] = (separator,) if limit is None else (separator, limit)
        if head == "rsplit" and overlaps_itself(separator) and not 0 <= (limit or -1) <= 16:
            continue
        count = len(_pieces(value, head, operands))
        listed = _listed(head, operands)
        for number in range(14, 22):
            asks.append((value, "Bool", listed.past(number)))
            expected.append(count > number)

    # past sixteen a compare is one membership, and an rsplit past its walk counts from the
    # start; strings with more pieces than sixteen are among them
    assert any(expected[at] for at in range(len(asks)) if at % 8 >= 3)
    assert asked(_program(asks)) == expected


def _from_the_end(listed: SplitList, pieces: list[str], back: int) -> tuple[int, bool]:
    """Where a piece ``back`` from the end is read, and whether it is there: by a walk of the
    reversed string on any string, but for an rsplit past its walk, else where c* puts it,
    there only on a string of c* pieces while the read holds it so, or else where the input's
    own count puts it."""
    unwalked = listed.head == "rsplit" and listed.limit() > LONGEST_WALK
    walked = not unwalked and right_piece("|s|", listed.head, listed.operands, back) is not None
    held = listed.read_count or 0
    at = len(pieces) - 1 - back if walked else held - 1 - back
    if not walked and listed.fixed:
        return at, len(pieces) == held and at >= 0
    return at, 0 <= at < len(pieces)


@needs_cvc5
def test_cvc5_reads_each_piece_from_the_end_as_python_does() -> None:
    rng = random.Random(5)
    asks: list[tuple[str, str, str]] = []
    expected: list[object] = []
    for _ in range(300):
        value = "".join(rng.choices(LETTERS, k=rng.randint(0, 7)))
        head, operands = _form(rng)
        pieces, back = _pieces(value, head, operands), rng.randint(0, 2)
        # c*: the string's own count, or one past or short of it, as another input's would be
        held = max(len(pieces) + rng.choice([-1, 0, 0, 1]), 0)
        listed = _listed(head, operands, held, fixed=rng.random() < 0.7)
        read = listed.read(Lin(-back - 1).plus(Lin.of(COUNT)), "str").found
        at, there = _from_the_end(listed, pieces, back)
        if read.value is None:
            # no piece that far from the end of the input's own pieces
            assert read.guard == FALSE and at < 0, (value, head, operands, back)
            continue
        asks += [(value, "Bool", read.guard), *([(value, "String", read.value)] if there else [])]
        expected += [there, *([pieces[at]] if there else [])]

    assert asked(_program(asks)) == expected


@pytest.mark.parametrize(
    ("position", "kind"),
    [(Lin.of("i"), "str"), (Lin.of(COUNT).plus(Lin(1)), "str"), (Lin(0), "int")],
    ids=["a term", "past the count", "another kind"],
)
def test_no_piece_is_read_at_another_position_or_of_another_kind(position: Lin, kind: str) -> None:
    # core keeps a split's list only where every read is from the start or the end: a tracked
    # index is a downgrade, and a list cut at a tracked bound is Python's own
    read = _listed("split", (",",), 3).read(position, kind)

    assert (read.found.value, read.found.guard, read.fixes_the_count) == (None, FALSE, False)


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


# a compare of a count with a number: the difference, whether it may be 0, and the count asked
BY_COUNT: dict[str, tuple[Lin, Lin, bool, str]] = {
    "count > 2": (Lin(2), Lin.of("c"), False, "P2"),
    "count >= 2": (Lin(2), Lin.of("c"), True, "P1"),
    "count + 1 > 3": (Lin(3), Lin.of("c").plus(Lin(1)), False, "P2"),
    "count < 3": (Lin.of("c"), Lin(3), False, "(not P2)"),
    "count <= 3": (Lin.of("c"), Lin(3), True, "(not P3)"),
    "count > -1": (Lin(-1), Lin.of("c"), False, "true"),
    "count < 0": (Lin.of("c"), Lin(0), False, "false"),
    "2 * count > 7": (Lin(7), Lin.of("c").times(2), False, "P3"),
    "2 * count >= 8": (Lin(8), Lin.of("c").times(2), True, "P3"),
    "2 * count < 9": (Lin.of("c").times(2), Lin(9), False, "(not P4)"),
    "3 * count <= 6": (Lin.of("c").times(3), Lin(6), True, "(not P2)"),
    "1 - count > -3": (Lin(-3), Lin(1).minus(Lin.of("c")), False, "(not P3)"),
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


def test_a_count_that_meets_a_tracked_int_is_c_star_with_no_tie() -> None:
    path = (fork(["==", ["len", SPLIT], "n"], taken=True),)
    values = {"s": "a,b,c", "n": 0}

    text = program(path, {"s": str, "n": int}, Origin(values=values)).text.splitlines()

    assert [line for line in text if "count!0!" in line] == [
        "(define-fun count!0! () Int 3)",
        "(assert (= count!0! |arg.n|))",
    ]


@needs_cvc5
def test_a_count_with_no_input_value_is_a_miss() -> None:
    path = (fork(["==", ["len", SPLIT], "n"], taken=True),)

    # core tracks a split's list only for a string the solver works out from the input's
    # values; a program with none for it asks nothing
    assert isinstance(solve(path, {"s": str, "n": int}, 10.0), Unknown)


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


@needs_cvc5
def test_cvc5_counts_a_slice_of_every_split_as_python_does() -> None:
    rng = random.Random(19)
    asks: list[tuple[str, str, str]] = []
    expected: list[object] = []
    bounds = [None, -3, -1, 0, 1, 2, 4]
    for _ in range(200):
        value = "".join(rng.choices(LETTERS, k=rng.randint(0, 7)))
        head, operands = _form(rng)
        window = (rng.choice(bounds), rng.choice(bounds), rng.choice([None, 1, -1]))
        splits = Splits()
        listed = splits.made([head, "s", *(_written(operand) for operand in operands)], "|s|")
        cut = splits.cut(listed, (slice(*window),)).atoms[0][0]
        length = len(_pieces(value, head, operands)[slice(*window)])
        for number in range(-1, 4):
            asks.append((value, "Bool", splits.counts[cut](number)))
            expected.append(length > number)

    assert asked(_program(asks)) == expected


def _written(operand: object) -> Expression:
    """An operand as core writes it in a form: a quoted string, a number, a bool or None."""
    if isinstance(operand, str):
        return repr(operand)
    assert operand is None or isinstance(operand, int)
    return operand
