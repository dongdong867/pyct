import dataclasses
from collections.abc import Callable

import pytest

from pyct.core.branch import Branch, BranchSink, Downgrade, Site, caller_site

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


def test_a_downgrade_names_the_call_that_dropped_the_condition() -> None:
    downgrade = Downgrade(name="__abs__")

    assert downgrade.name == "__abs__"


def test_a_plain_list_is_a_branch_sink() -> None:
    sink: BranchSink = []

    sink.append(Branch(expression="x", taken=True, site=Site(file="m.py", line=1, col=0)))

    assert sink == [Branch(expression="x", taken=True, site=Site(file="m.py", line=1, col=0))]


def test_a_sink_holds_forks_and_downgrades_in_the_order_they_happened() -> None:
    sink: BranchSink = []
    branch = Branch(expression="x", taken=True, site=Site(file="m.py", line=1, col=0))

    sink.append(Downgrade(name="__abs__"))
    sink.append(branch)

    assert sink == [Downgrade(name="__abs__"), branch]
