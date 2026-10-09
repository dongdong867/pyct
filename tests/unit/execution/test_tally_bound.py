"""The bound on the forks one call keeps: past it the call keeps no fork or fact, tells its
watch of none, and its ending is `too_long`, while its lines and downgrades still count."""

import pytest

from pyct.core import values
from pyct.core.branch import Branch, Downgrade, Fact, Site
from pyct.execution import tally
from pyct.execution.execute import ExecutionContext, execute
from pyct.execution.tally import Tally
from pyct.results.failure import Failure, FailureKind
from tests.unit.execution.test_tally import Heard

SITE = Site(file="t.py", line=3, col=7)


def _fork(number: int) -> Branch:
    return Branch(expression=[">", "x", number], taken=True, site=SITE)


def test_a_tally_keeps_the_forks_up_to_its_bound_and_then_only_lines_and_downgrades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tally, "MOST_FORKS", 2)
    heard = Heard()
    kept = Tally(heard)

    for number in range(4):
        kept.append(_fork(number))
    kept.append(Fact(expression=["==", "x", 1], taken=True, site=SITE))
    kept.line(9)
    kept.append(Downgrade(name="__xor__", site=SITE))

    assert kept.past_bound
    assert kept.branches == [_fork(0), _fork(1)]
    assert kept.facts == []
    assert heard.told == [
        ("fork", _fork(0)),
        ("fork", _fork(1)),
        ("line", 9),
        ("downgrade", "__xor__", 1),
    ]


def test_a_tally_within_its_bound_is_not_past_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tally, "MOST_FORKS", 2)
    kept = Tally()

    kept.append(_fork(0))
    kept.append(_fork(1))

    assert not kept.past_bound


def _counts(x: int) -> int:
    steps = 0
    while x > 0:
        x -= 1
        steps += 1
    return steps


def test_a_call_past_the_bound_ends_too_long_with_the_forks_before_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tally, "MOST_FORKS", 50)

    result = execute(ExecutionContext(fn=_counts, file=__file__), {"x": 1_000})

    assert result.failure == Failure(
        FailureKind.TOO_LONG, "the input took more than 50 forks, the most pyct keeps for one input"
    )
    assert len(result.branches) == 50
    # the `return` the call reaches after the bound still counts
    assert len(result.lines) == 5


def test_a_call_at_the_bound_keeps_its_own_ending(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tally, "MOST_FORKS", 4)

    # three passes and the last test: four forks, none past the bound
    result = execute(ExecutionContext(fn=_counts, file=__file__), {"x": 3})

    assert result.failure is None
    assert len(result.branches) == 4


def test_a_pyct_bug_after_the_bound_is_still_a_pyct_bug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tally, "MOST_FORKS", 2)
    calls = {"n": 0}
    real = values.caller_site

    def breaks_late() -> Site:
        calls["n"] += 1
        if calls["n"] > 3:
            raise RuntimeError("boom")
        return real()

    # each pass's compare reaches this through `ConcolicBool.__bool__`, a frame of pyct's own
    monkeypatch.setattr(values, "caller_site", breaks_late)

    result = execute(ExecutionContext(fn=_counts, file=__file__), {"x": 10})

    assert result.failure is not None
    assert result.failure.kind is FailureKind.PYCT_BUG
    assert result.failure.detail == "RuntimeError: boom"
