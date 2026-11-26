"""The runs a summaries request shows of a loss site's complete runs, and the inputs run again
once a formula comes into use.

A complete run is a recorded run of the site whose values going in fit its
code (`pyct.run.summary_checks.CompleteRun`). A request shows up to
``SHOWN_RUNS`` of them: the run its site's last formula was dropped on
first, then those whose values differ. When the runs hold two or more
different values going in, it holds back each run whose values going in are
those of one run, chosen so that the check, which runs on every complete
run, runs on values the model did not see, and so that a formula that
leaves the changed names as they came in fails there when a run lets it
(``_held_back``).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pyct.binding.bind import Seed
from pyct.core.entry.losses import ANSWER
from pyct.results.record import Source, Stop
from pyct.run.stuck import Running
from pyct.run.summary_checks import AskedRun, CompleteRun
from pyct.run.target import Target, argument_checks

if TYPE_CHECKING:
    from pyct.run.call_summaries import AskedCall

# the recorded runs a request shows at most
SHOWN_RUNS = 10


@dataclass(frozen=True)
class ShownRun:
    """One recorded run of the loss site as a request shows it: each parameter with its value
    going in, and the answer, each value JSON text."""

    going_in: tuple[tuple[str, str], ...]
    changed: tuple[tuple[str, str], ...]


def shown_runs(call: AskedCall, first: CompleteRun | None = None) -> tuple[ShownRun, ...]:
    """Up to ``SHOWN_RUNS`` of the site's complete runs, as values, but those held back:
    ``first`` when they hold it, then those whose values going in differ from every earlier
    one's, then those whose changed values differ, then the rest, each group in run order."""
    every = [_shown(each.run, call) for each in call.runs]
    picked = [call.runs.index(first)] if first in call.runs else []
    held = _held_back(every, picked)
    left = [at for at, each in enumerate(every) if each.going_in != held]
    for part in ("going_in", "changed"):
        seen = {getattr(every[at], part) for at in picked}
        for at in left:
            if at not in picked and getattr(every[at], part) not in seen:
                seen.add(getattr(every[at], part))
                picked.append(at)
    picked += [at for at in left if at not in picked]
    return tuple(every[at] for at in picked[:SHOWN_RUNS])


def _held_back(every: list[ShownRun], first: list[int]) -> tuple[tuple[str, str], ...] | None:
    """The values going in of the runs a request holds back, among the runs whose values going
    in differ from the run shown ``first``'s; None when every run has the same values going in.
    The run picked is the latest of the first kind that holds one: a run whose changed values no
    run with other values going in has and that moved a changed name (``_moved``); a run that
    moved one; a run whose changed values are its own; any run. On a run of the first two
    kinds, a formula that gives each changed name its value going in fails."""
    kept = {every[at].going_in for at in first}
    later = [each for each in reversed(every) if each.going_in not in kept]
    if not later or len({each.going_in for each in every}) < 2:
        return None
    going_in_of: dict[tuple[tuple[str, str], ...], set[tuple[tuple[str, str], ...]]] = {}
    for each in every:
        going_in_of.setdefault(each.changed, set()).add(each.going_in)

    def alone(run: ShownRun) -> bool:
        return going_in_of[run.changed] == {run.going_in}

    kinds = (lambda run: alone(run) and _moved(run), _moved, alone)
    picked = (next((run for run in later if kind(run)), None) for kind in kinds)
    return next((run for run in picked if run is not None), later[0]).going_in


def _moved(run: ShownRun) -> bool:
    """Whether the run left a changed name with a value other than the one it went in with, or
    one it did not go in with."""
    going_in = dict(run.going_in)
    return any(going_in.get(name) != value for name, value in run.changed)


def not_shown(call: AskedCall, shown: Sequence[ShownRun]) -> int:
    """The site's complete runs whose values going in no run of ``shown`` has."""
    seen = {each.going_in for each in shown}
    return sum(_shown(each.run, call).going_in not in seen for each in call.runs)


def _shown(run: AskedRun, call: AskedCall) -> ShownRun:
    going_in = tuple((each.name, each.value) for each in run.going_in)
    changed = {each.name: each.value for each in run.changed}
    return ShownRun(
        tuple(pair for pair in going_in if pair[0] in call.parameters),
        ((ANSWER, changed[ANSWER]),),
    )


def run_again(run: Running, numbers: Iterable[int], target: Target) -> None:
    """Run again each input ``numbers`` names, by its number in the run, from 1, once, in run
    order, labeled ``summary``, with no plan: the inputs a moment's formulas were checked on, so
    that each formula in use gives the solver its forks. Stops once one meets a stop."""
    checks = argument_checks(target)
    for number in sorted(set(numbers)):
        args = run.records[number - 1].args
        if isinstance(run.run_input(Seed.of(args, checks, target.home), Source.SUMMARY), Stop):
            return
