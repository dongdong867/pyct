"""A journal that fills is the bound on what pyct keeps for one input, so the input's own: its
line ends `too_long` with the facts before it, while a fact pyct cannot encode stays pyct's.
"""

from pyct.core.branch import Branch, Site
from pyct.run.journal import RECORDS, JournalWriter
from pyct.run.journal_reader import read

SITE = Site(file="t.py", line=3, col=7)


def test_a_full_journal_is_the_input_s_bound_not_a_problem() -> None:
    size = RECORDS + 4096
    buffer = bytearray(size)
    writer = JournalWriter(buffer)

    for line in range(10_000):
        writer.line(line)

    reading = read(buffer)
    assert reading.problem is None
    assert reading.bound == f"the journal is full at {size} bytes"


def test_an_unencodable_fact_stays_a_problem_and_sets_no_bound() -> None:
    buffer = bytearray(RECORDS + 4096)
    writer = JournalWriter(buffer)

    writer.fork(Branch(expression=["==", "x", object()], taken=True, site=SITE))  # type: ignore[list-item]

    reading = read(buffer)
    assert reading.bound is None
    assert reading.problem == "could not keep a fork the input took: a leaf of type object"
