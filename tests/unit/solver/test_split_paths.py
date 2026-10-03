"""The splits of one path as the program writes them: c*, the count a term that meets the
count reads and a read from the end puts its piece at, which the forks on a split's own count
through plain arithmetic narrow, and each count a line reads, written as its c*."""

import random
import re

import pytest

from pyct.core.branch import Expression
from pyct.solver.split_counts import windowed, windows_past
from pyct.solver.split_paths import Splits
from tests.unit.solver.test_render import fork

PARTS: list[Expression] = ["split", "s", "','"]
LENGTH: Expression = ["len", PARTS]
# the input's string, with twelve pieces
TWELVE = ",".join("a" * 12)

# the forks on the split's length, each with the side taken, and the count a read from the end
# of twelve pieces is read at
RANGES: dict[str, tuple[list[tuple[Expression, bool]], int]] = {
    "more than, taken": ([([">", LENGTH, 20], True)], 21),
    "at least, taken": ([([">=", LENGTH, 15], True)], 15),
    "fewer than, taken": ([(["<", LENGTH, 5], True)], 4),
    "at most, taken": ([(["<=", LENGTH, 5], True)], 5),
    "equal, taken": ([(["==", LENGTH, 7], True)], 7),
    "more than, not taken": ([([">", LENGTH, 5], False)], 5),
    "at least, not taken": ([([">=", LENGTH, 5], False)], 4),
    "fewer than, not taken": ([(["<", LENGTH, 15], False)], 15),
    "at most, not taken": ([(["<=", LENGTH, 15], False)], 16),
    "not equal, not taken": ([(["!=", LENGTH, 7], False)], 7),
    "not equal, taken": ([(["!=", LENGTH, 7], True)], 12),
    "equal, not taken": ([(["==", LENGTH, 7], False)], 12),
    "a number fewer than it": ([(["<", 20, LENGTH], True)], 21),
    "a number at most it": ([(["<=", 15, LENGTH], True)], 15),
    "a number more than it": ([([">", 5, LENGTH], True)], 4),
    "a number at least it": ([([">=", 5, LENGTH], True)], 5),
    "a number equal to it": ([(["==", 7, LENGTH], True)], 7),
    "a number not equal to it, not taken": ([(["!=", 7, LENGTH], False)], 7),
    "two forks between": ([([">", LENGTH, 3], True), (["<", LENGTH, 6], True)], 5),
    "a length the forks leave alone": ([([">", LENGTH, 3], True)], 12),
    "less one, more than": ([([">", ["-", LENGTH, 1], 20], True)], 22),
    "doubled, fewer than": ([(["<", ["*", 2, LENGTH], 9], True)], 4),
    "a slice's length": ([([">", ["len", ["[:]", PARTS, 2, None]], 15], True)], 18),
    "a floor division": ([(["<", ["//", LENGTH, 2], 3], True)], 12),
    "a tracked int": ([([">", LENGTH, "n"], False)], 12),
    "ruled out": ([([">", LENGTH, 5], True), (["<", LENGTH, 3], True)], 12),
    "a slice of a slice": (
        [([">", ["len", ["[:]", ["[:]", PARTS, 1, None], 1, None]], 15], True)],
        18,
    ),
    "a display joined on": ([([">", ["len", ["+", PARTS, ["[,]", "'z'"]]], 15], True)], 15),
    "a display joined before": (
        [([">", ["len", ["+", ["[,]", "'z'", "'y'"], PARTS]], 15], True)],
        14,
    ),
    "a repeat": ([([">", ["len", ["*", PARTS, 2]], 30], True)], 12),
}


@pytest.mark.parametrize(("forks", "count"), RANGES.values(), ids=list(RANGES))
def test_a_read_from_the_end_is_put_at_the_count_the_forks_allow_nearest_the_input_s(
    forks: list[tuple[Expression, bool]], count: int
) -> None:
    splits = Splits()
    splits.given = lambda part: TWELVE if part == "s" else None
    splits.learn(tuple(fork(expression, taken=taken) for expression, taken in forks))

    listed = splits.made(PARTS, "s")

    assert listed.input_count == 12
    assert listed.read_count == count


def test_each_count_a_line_reads_is_written_once_as_its_c_star() -> None:
    splits = Splits()
    splits.given = lambda part: TWELVE if part == "s" else None
    listed = splits.made(PARTS, "s")
    other = splits.made(["split", "t", "','"], "t")
    cut = splits.cut(listed, (slice(2, None, None),)).atoms[0][0]

    first = splits.defined([f"(> {listed.count} n)", f"(< {cut} 3)"])
    again = splits.defined([f"(> {listed.count} n)", f"(= {other.count} 1)"])

    assert first == [f"(define-fun {listed.count} () Int 12)", f"(define-fun {cut} () Int 10)"]
    # t's value is not known: its count is a count no tie holds
    assert again == [f"(declare-const {other.count} Int)", f"(assert (>= {other.count} 0))"]


@pytest.mark.parametrize(
    ("string", "count"),
    [
        (["strip", "s"], 12),
        (["lower", ["strip", "s"]], 12),
        (["+", "s", "t"], None),
        (["+", "s", "','"], 13),
        (["*", "s", 2], 23),
        (["*", "s", 10**7], None),
        (["[]", ["split", ["strip", "s"], "';'"], 0], 12),
        (["[:]", ["strip", "s"], 2, None], 11),
        (["format", "s"], None),
        (["+", (twice := ["*", "s", 2]), twice], 45),
        (["+", (long := ["*", "s", 80_000]), long], None),
    ],
    ids=[
        "a method",
        "two methods",
        "an unknown name",
        "a join",
        "a repeat",
        "a repeat past the longest",
        "a piece",
        "a slice",
        "a method not worked out",
        "one part twice",
        "a join past the longest",
    ],
)
def test_a_string_a_method_makes_of_the_input_s_is_counted(
    string: Expression, count: int | None
) -> None:
    splits = Splits()
    splits.given = lambda part: f" {TWELVE} " if part == "s" else None

    listed = splits.made(["split", string, "','"], "s")

    assert listed.input_count == count


def test_a_cut_s_length_is_more_than_a_number_where_python_s_is() -> None:
    rng = random.Random(23)
    bounds = [None, -7, -3, -1, 0, 1, 2, 5]
    for _ in range(2000):
        windows = tuple(
            slice(rng.choice(bounds), rng.choice(bounds), rng.choice([None, 1, -1]))
            for _ in range(rng.randint(1, 3))
        )
        number = rng.randint(-1, 9)
        # read with a count of `count` pieces, piece j is there where the count is past j
        written = windows_past(lambda j: f"(> c {j})", windows, number)
        for count in range(0, 90):
            python = (
                len(range(count)[windows[0]]) if len(windows) == 1 else windowed(windows, count)
            )
            assert _holds(written, count) is (python > number), (windows, number, count)


def _holds(condition: str, count: int) -> bool:
    """A condition ``windows_past`` writes, read where the count is ``count``."""
    text = re.sub(r"\(> c (-?\d+)\)", lambda found: str(count > int(found[1])), condition)
    text = text.replace("true", "True").replace("false", "False")
    while "(" in text:
        text = re.sub(
            r"\((and|or|not) ([^()]*)\)",
            lambda found: str(_apply(found[1], found[2].split())),
            text,
        )
    return text == "True"


def _apply(head: str, values: list[str]) -> bool:
    truths = [value == "True" for value in values]
    return all(truths) if head == "and" else any(truths) if head == "or" else not truths[0]
