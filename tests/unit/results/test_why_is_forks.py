"""An `is` test's sides as see-why reads them from the forks the test recorded of its own."""

import textwrap
from pathlib import Path

from pyct.core.branch import Branch, Fact, Site
from pyct.results.why import Condition, Run, Walked, explain

NAMED = """\
FLAG = False


def f(x):
    n = 0
    if (x < 9) is FLAG:
        n += 1
    return n
"""


def module(tmp_path: Path, source: str) -> str:
    file = tmp_path / "m.py"
    file.write_text(textwrap.dedent(source))
    return str(file)


def body_condition(file: str, walked: Walked, body: int) -> Condition | None:
    """The condition named for the line ``body``, which no input ran."""
    entries = explain(file, frozenset({body}), walked.lines, Run([walked], {}))
    (entry,) = entries
    return entry.condition


def test_a_test_s_own_fork_reads_in_its_pass_s_sense(tmp_path: Path) -> None:
    file = module(tmp_path, NAMED)
    site = Site(file, 6, 7)
    # x < 9 held, and the `is` against False did not
    fork = Branch(["<", "x", 9], True, site, is_held=False)

    condition = body_condition(file, Walked((fork,), False, frozenset({5, 6, 8})), 7)

    assert condition == Condition(site, False)


def test_a_fork_with_no_note_at_the_test_reads_as_before(tmp_path: Path) -> None:
    file = module(tmp_path, NAMED)
    site = Site(file, 6, 7)
    fork = Branch(["<", "x", 9], True, site)

    condition = body_condition(file, Walked((fork,), False, frozenset({5, 6, 8})), 7)

    # no input ran the body, so nothing shows the sense: the `is` sense
    assert condition == Condition(site, True)


DECIDED = """\
FLAG = False


def f(d):
    if bool(d) is FLAG:
        return 1
    else:
        return 2
"""


# read-an-is-test-against-a-name-per-pass-reads-a-decided-check-at-a-test-as-before
def test_a_decided_check_at_a_test_reads_as_before(tmp_path: Path) -> None:
    file = module(tmp_path, DECIDED)
    site = Site(file, 5, 7)
    # no fork at the test, only a decided check there that held; the `else` alone ran
    decided = Fact(["!=", ["len", "d"], 0], True, site)

    condition = body_condition(file, Walked((), False, frozenset({5, 8}), (decided,)), 6)

    # the `else` reads as the operand's true side, so the body as its false side
    assert condition == Condition(site, False)
