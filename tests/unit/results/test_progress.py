"""Progress reads, from what each input reached, whether every line and branch is covered."""

from pyct.results.coverage import Progress, Reach, Scope

# a module of lines 1 to 9: `def f` on 1 with lines 2 to 5, line 3 a branch to 4 and 5; `def g`
# on 6 with lines 7 to 9, which no input enters
SCOPE = Scope(file="m.py", lines=frozenset(range(1, 10)))
IMPORTED = frozenset({1, 6})
F = Reach(lines=frozenset({1, 2, 3, 4, 5}), branches={3: frozenset({4, 5})})


def entered_f(lines: set[int], went: set[tuple[int, int]]) -> tuple[frozenset[int], Reach]:
    """An input that entered ``f``, covered ``lines`` and went ``went``."""
    return frozenset(lines), Reach(lines=F.lines, branches=F.branches, went=frozenset(went))


def test_full_once_every_line_and_each_way_of_a_reached_branch_is_covered() -> None:
    progress = Progress(SCOPE, IMPORTED)

    progress.add(*entered_f({2, 3, 4}, {(3, 4)}))
    assert not progress.full()
    progress.add(*entered_f({2, 3, 5}, {(3, 5)}))

    # `g`, which no input entered, keeps nothing from it
    assert progress.full()


def test_not_full_while_a_branch_went_one_way_though_every_line_is_covered() -> None:
    progress = Progress(SCOPE, IMPORTED)

    progress.add(*entered_f({2, 3, 4, 5}, {(3, 4)}))

    assert not progress.full()


def test_a_line_the_import_ran_counts_as_covered() -> None:
    progress = Progress(SCOPE, frozenset())

    progress.add(*entered_f({2, 3, 4, 5}, {(3, 4), (3, 5)}))
    assert not progress.full()
    imported = Progress(SCOPE, IMPORTED)
    imported.add(*entered_f({2, 3, 4, 5}, {(3, 4), (3, 5)}))

    assert imported.full()


def test_a_branch_no_input_reached_does_not_count() -> None:
    progress = Progress(SCOPE, IMPORTED)
    unreached = Reach(lines=frozenset({1, 2}), branches={8: frozenset({7, 9})})

    progress.add(frozenset({2}), unreached)

    assert progress.full()


def test_never_full_when_no_input_entered_a_function() -> None:
    progress = Progress(SCOPE, IMPORTED)

    progress.add(frozenset(), Reach())

    assert not progress.full()


def test_keeps_each_input_s_lines_within_the_scope_in_run_order() -> None:
    progress = Progress(SCOPE, IMPORTED)

    progress.add(frozenset({2, 99}), Reach())
    progress.add(frozenset({3}), Reach())

    assert progress.covered == [frozenset({2}), frozenset({3})]
