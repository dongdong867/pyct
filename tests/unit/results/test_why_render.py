"""A cause as the summary line writes it, and as the stderr trace writes it."""

import pytest

from pyct.core.branch import Site
from pyct.results.why import Condition, Reason, Tries, WhyEntry
from pyct.results.why_render import why_json, why_line

AT = Condition(site=Site(file="m.py", line=3, col=7), side=True)


def test_an_entry_writes_its_file_lines_and_reason_then_what_its_reason_names() -> None:
    entry = WhyEntry("m.py", (4,), Reason.NOT_TAKEN, condition=AT, tries=Tries(unsat=1))

    assert why_json(entry) == {
        "file": "m.py",
        "lines": [4],
        "reason": "not taken",
        "condition": {"file": "m.py", "line": 3, "col": 7, "side": True},
        "tries": {
            "not_tried": 0,
            "unsat": 1,
            "unknown": 0,
            "timeout": 0,
            "left_the_plan": 0,
            "decided": 0,
        },
    }


def test_an_entry_leaves_out_what_its_reason_does_not_name() -> None:
    assert why_json(WhyEntry("m.py", (1, 3), Reason.IMPORT)) == {
        "file": "m.py",
        "lines": [1, 3],
        "reason": "import",
    }
    assert why_json(WhyEntry("m.py", (8,), Reason.NOT_CALLED, function="helper")) == {
        "file": "m.py",
        "lines": [8],
        "reason": "not called",
        "function": "helper",
    }
    assert why_json(WhyEntry("m.py", (4,), Reason.NO_FORK, condition=AT))["condition"] == {
        "file": "m.py",
        "line": 3,
        "col": 7,
        "side": True,
    }


@pytest.mark.parametrize(
    ("entry", "line"),
    [
        (WhyEntry("m.py", (1, 3, 7), Reason.IMPORT), "why 1, 3, 7 in m.py: import"),
        (
            WhyEntry("m.py", (8, 9), Reason.NOT_CALLED, function="helper"),
            "why 8, 9 in m.py: helper not called",
        ),
        (
            WhyEntry("m.py", (4,), Reason.NOT_TAKEN, condition=AT, tries=Tries(unsat=1)),
            "why 4 in m.py: m.py:3:7 never true: 1 unsat",
        ),
        (
            WhyEntry(
                "m.py",
                (5,),
                Reason.NOT_TAKEN,
                condition=Condition(site=Site(file="m.py", line=4, col=7), side=False),
                tries=Tries(not_tried=2, timeout=1, left_the_plan=3),
            ),
            "why 5 in m.py: m.py:4:7 never false: 2 not tried, 1 timeout, 3 left the plan",
        ),
        (
            WhyEntry("m.py", (5,), Reason.NOT_TAKEN, condition=AT, tries=Tries()),
            "why 5 in m.py: m.py:3:7 never true",
        ),
        (
            WhyEntry("m.py", (5,), Reason.NO_FORK, condition=AT),
            "why 5 in m.py: m.py:3:7 never true, no fork",
        ),
        (WhyEntry("m.py", (12,), Reason.HANDLER), "why 12 in m.py: in a handler no raise reached"),
        (
            WhyEntry("m.py", (15,), Reason.ENDED_BEFORE),
            "why 15 in m.py: every input that got there ended before it",
        ),
    ],
)
def test_each_reason_has_its_own_words_on_stderr(entry: WhyEntry, line: str) -> None:
    assert why_line(entry) == line


def test_a_suspended_entry_names_the_yield_it_stopped_at() -> None:
    entry = WhyEntry("m.py", (3, 4), Reason.SUSPENDED, at_yield=2)

    assert why_json(entry) == {
        "file": "m.py",
        "lines": [3, 4],
        "reason": "suspended",
        "yield": {"file": "m.py", "line": 2},
    }
    assert why_line(entry) == "why 3, 4 in m.py: suspended at the yield on m.py:2"
