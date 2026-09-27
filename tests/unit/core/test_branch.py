import dataclasses
import weakref
from collections.abc import Callable

import pytest

from pyct.core import branch as core_branch
from pyct.core.branch import Branch, BranchSink, Downgrade, SinkItem, Site, caller_site
from pyct.core.ints import ConcolicInt

# a probe whose text is fixed here, so the file, line and column asserted below are exact
PROBE = "def probe(site_of):\n    return site_of()\n"


def _probe() -> Callable[..., object]:
    namespace: dict[str, object] = {}
    exec(compile(PROBE, "<probe>", "exec"), namespace)
    probe = namespace["probe"]
    assert callable(probe)
    return probe


def test_site_and_branch_hold_their_fields() -> None:
    branch = Branch(expression=["<", "x", 10], taken=True, site=Site(file="m.py", line=5, col=7))

    assert branch.expression == ["<", "x", 10]
    assert branch.taken is True
    assert branch.site == Site(file="m.py", line=5, col=7)


def test_a_branch_cannot_be_changed() -> None:
    branch = Branch(expression="x", taken=False, site=Site(file="m.py", line=1, col=0))

    with pytest.raises(dataclasses.FrozenInstanceError):
        branch.taken = True  # type: ignore[misc]


def test_caller_site_reports_the_callers_file_line_and_column() -> None:
    site = _probe()(caller_site)

    # `site_of()` starts at column 11 of line 2 of the probe; pyct's own frame is skipped
    assert site == Site(file="<probe>", line=2, col=11)


def test_caller_site_hands_back_the_site_it_found_for_the_same_instruction() -> None:
    probe = _probe()

    first, again = probe(caller_site), probe(caller_site)

    # a loop asks on every pass; the second answer is the one object the first found
    assert first is again


def test_caller_site_finds_the_site_again_when_its_code_is_not_the_one_it_kept() -> None:
    probe = _probe()
    found = probe(caller_site)
    # what a freed code whose id the probe's code now has would leave behind
    stale = compile("pass", "<stale>", "exec")
    for key, (_, site) in list(core_branch._SITES.items()):
        if site is found:
            core_branch._SITES[key] = (weakref.ref(stale), Site(file="<stale>", line=1, col=0))
    # another site found since, so the answer is not the last one kept
    core_branch._LAST[0] = (stale, 0, Site(file="<stale>", line=1, col=0))

    assert probe(caller_site) == Site(file="<probe>", line=2, col=11)


def test_a_downgrade_names_the_call_that_dropped_the_condition_and_where() -> None:
    downgrade = Downgrade(name="__abs__", site=Site(file="m.py", line=2, col=8))

    assert downgrade.name == "__abs__"
    assert downgrade.site == Site(file="m.py", line=2, col=8)


def test_an_untaught_operation_records_the_site_of_the_call() -> None:
    namespace: dict[str, object] = {}
    exec(compile("def lose(x):\n    return x ^ 0\n", "<lost>", "exec"), namespace)
    lose = namespace["lose"]
    assert callable(lose)
    sink: list[SinkItem] = []

    lose(ConcolicInt(3, expression="x", sink=sink))

    # the target's `x ^ 0`, at column 11 of its line 2; pyct's own frames are skipped
    assert sink == [Downgrade(name="__xor__", site=Site(file="<lost>", line=2, col=11))]


def test_a_plain_list_is_a_branch_sink() -> None:
    sink: BranchSink = []

    sink.append(Branch(expression="x", taken=True, site=Site(file="m.py", line=1, col=0)))

    assert sink == [Branch(expression="x", taken=True, site=Site(file="m.py", line=1, col=0))]


def test_a_sink_holds_forks_and_downgrades_in_the_order_they_happened() -> None:
    sink: BranchSink = []
    branch = Branch(expression="x", taken=True, site=Site(file="m.py", line=1, col=0))

    downgrade = Downgrade(name="__abs__", site=Site(file="m.py", line=1, col=4))
    sink.append(downgrade)
    sink.append(branch)

    assert sink == [downgrade, branch]


def test_a_truth_test_s_fork_is_not_marked_as_an_operation_s() -> None:
    sink: list[SinkItem] = []

    bool(ConcolicInt(3, expression="x", sink=sink))

    assert [item.raising for item in sink if isinstance(item, Branch)] == [False]


def test_a_fork_before_an_operation_that_may_raise_is_marked_as_the_operation_s() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    10 // x
    bool(x)

    # the division's zero fork is marked; the plain truth test after it is not, so the mark
    # does not outlive the division
    assert [item.raising for item in sink if isinstance(item, Branch)] == [True, False]


def test_a_repeated_downgrade_at_one_instruction_is_the_one_object() -> None:
    namespace: dict[str, object] = {}
    source = "def spin(x):\n    for _ in range(3):\n        x ^ 0\n    return x ^ 1\n"
    exec(compile(source, "<spun>", "exec"), namespace)
    spin = namespace["spin"]
    assert callable(spin)
    sink: list[SinkItem] = []

    spin(ConcolicInt(3, expression="x", sink=sink))

    first, second, third, last = sink
    assert first is second is third
    assert last == Downgrade(name="__xor__", site=Site(file="<spun>", line=4, col=11))


def test_another_name_at_the_same_instruction_is_another_downgrade() -> None:
    namespace: dict[str, object] = {}
    exec(compile("def both(x, f):\n    return f(x)\n", "<both>", "exec"), namespace)
    both = namespace["both"]
    assert callable(both)
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    both(x, float)
    both(x, str)

    # one call instruction, two methods lost through it
    assert [item.name for item in sink if isinstance(item, Downgrade)] == ["__float__", "__str__"]
