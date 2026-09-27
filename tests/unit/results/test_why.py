"""Why each uncovered line was missed: one cause a line, read from the code and the run."""

import textwrap
from collections.abc import Sequence
from pathlib import Path

from pyct.core.branch import Branch, ForkSite, Site
from pyct.results.why import Condition, Reason, Run, Tries, Walked, WhyEntry, explain


def module(tmp_path: Path, source: str) -> str:
    """A target module on disk, as the run measured it; the path is the coverage map's key."""
    file = tmp_path / "m.py"
    file.write_text(textwrap.dedent(source))
    return str(file)


def fork(file: str, line: int, col: int, *, taken: bool, raising: bool = False) -> Branch:
    site = Site(file=file, line=line, col=col)
    return Branch(expression=["<", "x", 0], taken=taken, site=site, raising=raising)


def why(
    file: str,
    lines: tuple[set[int], set[int]],
    walked: Sequence[Walked] = (),
    tries: dict[ForkSite, Tries] | None = None,
) -> tuple[WhyEntry, ...]:
    """``explain`` over one file: its uncovered lines, then its covered ones."""
    uncovered, covered = lines
    return explain(file, frozenset(uncovered), frozenset(covered), Run(walked, tries or {}))


UNTAKEN = """\
def same(x):
    # nothing is ever unequal to itself
    if x != x:
        return "never"
    return "always"
"""


def test_a_line_whose_side_no_input_took_names_the_condition_and_its_tries(
    tmp_path: Path,
) -> None:
    file = module(tmp_path, UNTAKEN)
    site = Site(file=file, line=3, col=7)
    walked = [Walked(forks=(fork(file, 3, 7, taken=False),), failed=False)]

    entries = why(file, ({1, 4}, {3, 5}), walked, {ForkSite(site): Tries(unsat=1)})

    assert entries == (
        WhyEntry(file=file, lines=(1,), reason=Reason.IMPORT),
        WhyEntry(
            file=file,
            lines=(4,),
            reason=Reason.NOT_TAKEN,
            condition=Condition(site=site, side=True),
            tries=Tries(unsat=1),
        ),
    )


def test_a_condition_with_no_tries_counts_none(tmp_path: Path) -> None:
    file = module(tmp_path, UNTAKEN)
    walked = [Walked(forks=(fork(file, 3, 7, taken=False),), failed=False)]

    (entry,) = why(file, ({4}, {3, 5}), walked)

    assert entry.tries == Tries()


def test_a_function_no_input_entered_is_named(tmp_path: Path) -> None:
    source = """\
    def f(x):
        return x


    class Cart:
        def total(self):
            n = 1
            return n
    """
    file = module(tmp_path, source)

    entries = why(file, ({1, 5, 6, 7, 8}, {2}))

    assert entries == (
        WhyEntry(file=file, lines=(1, 5, 6), reason=Reason.IMPORT),
        WhyEntry(file=file, lines=(7, 8), reason=Reason.NOT_CALLED, function="Cart.total"),
    )


def test_a_plain_condition_whose_side_no_input_took_recorded_no_fork(tmp_path: Path) -> None:
    source = """\
    def big(x):
        c = x ^ 0
        if c > 10:
            return "big"
        return "small"
    """
    file = module(tmp_path, source)

    (entry,) = why(file, ({4}, {2, 3, 5}))

    assert entry == WhyEntry(
        file=file,
        lines=(4,),
        reason=Reason.NO_FORK,
        condition=Condition(site=Site(file=file, line=3, col=7), side=True),
    )


def test_the_first_untaken_side_on_the_way_is_blamed_for_every_line_behind_it(
    tmp_path: Path,
) -> None:
    source = """\
    def deep(x, y):
        # nothing is ever unequal to itself
        if x != x:
            if y > 0:
                return "deep"
        return "shallow"
    """
    file = module(tmp_path, source)
    walked = [Walked(forks=(fork(file, 3, 7, taken=False),), failed=False)]

    (entry,) = why(file, ({4, 5}, {3, 6}), walked)

    assert entry.lines == (4, 5)
    assert entry.condition == Condition(site=Site(file=file, line=3, col=7), side=True)


DIVIDES = """\
def divide(x):
    y = 10 // (x - x)
    return y
"""


def test_the_lines_after_a_raising_operation_need_its_fork_s_true_side(tmp_path: Path) -> None:
    file = module(tmp_path, DIVIDES)
    # the zero fork, taken false, and the input raised
    walked = [Walked(forks=(fork(file, 2, 8, taken=False, raising=True),), failed=True)]

    (entry,) = why(file, ({3}, {2}), walked)

    assert entry.reason is Reason.NOT_TAKEN
    assert entry.condition == Condition(site=Site(file=file, line=2, col=8), side=True)


def test_a_fork_an_input_went_on_past_on_its_false_side_is_no_raising_operation(
    tmp_path: Path,
) -> None:
    file = module(tmp_path, DIVIDES)
    walked = [Walked(forks=(fork(file, 2, 8, taken=False),), failed=False)]

    (entry,) = why(file, ({3}, {2}), walked)

    assert entry.reason is Reason.ENDED_BEFORE


def test_a_line_every_input_ended_before_says_so(tmp_path: Path) -> None:
    source = """\
    def ends(x):
        y = int("x")
        return y + x
    """
    file = module(tmp_path, source)

    assert why(file, ({3}, {2}), [Walked(forks=(), failed=True)]) == (
        WhyEntry(file=file, lines=(3,), reason=Reason.ENDED_BEFORE),
    )


HANDLER = """\
def parse(x):
    try:
        n = int(x)
    except ValueError:
        return "bad"
    return n
"""


def test_a_line_in_an_except_block_no_raise_reached_is_the_handler_s(tmp_path: Path) -> None:
    file = module(tmp_path, HANDLER)

    (entry,) = why(file, ({4, 5}, {2, 3, 6}))

    assert entry == WhyEntry(file=file, lines=(4, 5), reason=Reason.HANDLER)


def test_an_except_clause_a_raise_reached_but_did_not_match_is_still_the_handler_s(
    tmp_path: Path,
) -> None:
    file = module(tmp_path, HANDLER)

    entries = why(file, ({5, 6}, {2, 3, 4}), [Walked(forks=(), failed=True)])

    # the raise went on out of the function, so the line after the try is ended before
    assert entries == (
        WhyEntry(file=file, lines=(5,), reason=Reason.HANDLER),
        WhyEntry(file=file, lines=(6,), reason=Reason.ENDED_BEFORE),
    )


def test_a_line_in_a_handler_the_raise_entered_is_ended_before(tmp_path: Path) -> None:
    source = """\
    def parse(x):
        try:
            n = int(x)
        except ValueError:
            n = int("y")
            return n
        return n
    """
    file = module(tmp_path, source)

    walked = [Walked(forks=(), failed=True, lines=frozenset({2, 3, 4, 5}))]

    (entry,) = why(file, ({6, 7}, {2, 3, 4, 5}), walked)

    assert entry == WhyEntry(file=file, lines=(6, 7), reason=Reason.ENDED_BEFORE)


def test_a_finally_inside_a_handler_is_the_handler_s_by_either_of_its_copies(
    tmp_path: Path,
) -> None:
    source = """\
    def f(x):
        try:
            n = int(x)
        except ValueError:
            try:
                n = 0
            finally:
                x = 1
        return x
    """
    file = module(tmp_path, source)

    # line 8 is compiled twice, once for each way into the finally, both inside the handler;
    # the `finally:` line holds no instruction, so no run counts it
    assert why(file, ({4, 5, 6, 8}, {2, 3, 9})) == (
        WhyEntry(file=file, lines=(4, 5, 6, 8), reason=Reason.HANDLER),
    )


def test_a_side_runs_took_lets_the_walk_go_on_to_the_next_condition(tmp_path: Path) -> None:
    source = """\
    def f(x, y):
        if x > 0:
            if y > 0:
                return "both"
            c = y ^ 0
            if c < -5:
                return "low"
        return "none"
    """
    file = module(tmp_path, source)
    # `x > 0` recorded no fork, and line 3 shows a run took its true side
    walked = [Walked(forks=(fork(file, 3, 11, taken=False),), failed=False)]

    entries = why(file, ({4, 7}, {2, 3, 5, 6, 8}), walked)

    # past `x > 0`, `y > 0` was never true, and `c < -5`, plain, never true
    assert [(entry.lines, entry.reason) for entry in entries] == [
        ((4,), Reason.NOT_TAKEN),
        ((7,), Reason.NO_FORK),
    ]
    assert entries[1].condition == Condition(site=Site(file=file, line=6, col=11), side=True)


def test_a_condition_no_input_reached_leaves_the_line_ended_before(tmp_path: Path) -> None:
    source = """\
    def f(x):
        y = int("x")
        if x > 0:
            return y
        return 0
    """
    file = module(tmp_path, source)

    entries = why(file, ({3, 4, 5}, {2}), [Walked(forks=(), failed=True, lines=frozenset({2}))])

    assert entries == (WhyEntry(file=file, lines=(3, 4, 5), reason=Reason.ENDED_BEFORE),)


def test_forks_in_another_file_do_not_count_for_this_one(tmp_path: Path) -> None:
    file = module(tmp_path, UNTAKEN)
    elsewhere = str(tmp_path / "other.py")
    walked = [Walked(forks=(fork(elsewhere, 3, 7, taken=False),), failed=False)]

    (entry,) = why(file, ({4}, {3, 5}), walked)

    # the fork at 3:7 was another file's, so this file's condition there is plain
    assert entry.reason is Reason.NO_FORK


def test_a_run_that_covered_everything_reads_no_code(tmp_path: Path) -> None:
    assert why(str(tmp_path / "gone.py"), (set(), {1, 2})) == ()


def test_a_module_that_no_longer_reads_puts_each_line_down_to_the_import(tmp_path: Path) -> None:
    gone = str(tmp_path / "gone.py")
    broken = module(tmp_path, "def f(:\n")

    assert why(gone, ({2, 3}, {1})) == (WhyEntry(file=gone, lines=(2, 3), reason=Reason.IMPORT),)
    assert why(broken, ({1}, set())) == (WhyEntry(file=broken, lines=(1,), reason=Reason.IMPORT),)
