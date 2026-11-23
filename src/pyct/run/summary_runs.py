"""A loop's complete runs in a run's records, the runs a summaries request shows of them, and the
inputs run again once a formula comes into use.

A complete run is a recorded run of the loop that holds every name it
changes (`pyct.run.summary_checks.CompleteRun`). A request shows up to
``SHOWN_RUNS`` of them: the run its loop's last formula was dropped on
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

from pyct.binding.bind import Seed
from pyct.core.foundation.branch import FormulaDrop, PieceRun, Site
from pyct.results.pieces import Piece
from pyct.results.record import InputRecord, Source, Stop
from pyct.run.loops_in_use import statement_at
from pyct.run.stuck import Running
from pyct.run.summary_checks import CompleteRun
from pyct.run.target import Target, argument_checks

# the recorded runs a request shows at most
SHOWN_RUNS = 10


@dataclass(frozen=True)
class ShownRun:
    """One recorded run of the loop as a request shows it: each parameter with its value at the
    start, and each changed name with its value at the end, each value JSON text."""

    going_in: tuple[tuple[str, str], ...]
    changed: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class AskedLoop:
    """A loop at one moment: its site, its piece, its complete runs, and the formula's
    parameters."""

    site: Site
    piece: Piece
    runs: tuple[CompleteRun, ...]
    parameters: tuple[str, ...]


def asked_loop(site: Site, records: Sequence[InputRecord]) -> AskedLoop | None:
    """The loop at ``site`` with its complete runs in the records, oldest first, and the names
    going in that each holds; None when the site holds no piece or no run is complete."""
    piece = piece_at(site)
    if piece is None:
        return None
    wanted = set(piece.changed)
    runs = tuple(
        CompleteRun(number, each)
        for number, record in enumerate(records, start=1)
        for each in record.pieces
        if each.site == site and wanted <= {changed.name for changed in each.changed}
    )
    if not runs:
        return None
    held = [{going.name for going in each.run.going_in} for each in runs]
    parameters = tuple(name for name in piece.going_in if all(name in names for names in held))
    return AskedLoop(site, piece, runs, parameters)


def shown_runs(loop: AskedLoop, first: CompleteRun | None = None) -> tuple[ShownRun, ...]:
    """Up to ``SHOWN_RUNS`` of the loop's complete runs, as values, but those held back:
    ``first`` when they hold it, then those whose values going in differ from every earlier
    one's, then those whose changed values differ, then the rest, each group in run order."""
    every = [_shown(each.run, loop) for each in loop.runs]
    picked = [loop.runs.index(first)] if first in loop.runs else []
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
    """Whether the run's loop left a changed name with a value other than the one it went in
    with, or one it did not go in with."""
    going_in = dict(run.going_in)
    return any(going_in.get(name) != value for name, value in run.changed)


def not_shown(loop: AskedLoop, shown: Sequence[ShownRun]) -> int:
    """The loop's complete runs whose values going in no run of ``shown`` has."""
    seen = {each.going_in for each in shown}
    return sum(_shown(each.run, loop).going_in not in seen for each in loop.runs)


def _shown(run: PieceRun, loop: AskedLoop) -> ShownRun:
    going_in = tuple((each.name, each.value) for each in run.going_in)
    changed = {each.name: each.value for each in run.changed}
    return ShownRun(
        tuple(pair for pair in going_in if pair[0] in loop.parameters),
        tuple((name, changed[name]) for name in loop.piece.changed),
    )


def failed_run(drop: FormulaDrop, record: InputRecord, number: int) -> CompleteRun | None:
    """The run of the loop an input's drop names by its position, as the input's record holds
    it, the input numbered ``number``. None when the drop names no run or the record holds
    none there."""
    runs = [each for each in record.pieces if each.site == drop.site]
    if drop.run is None or not 0 <= drop.run < len(runs):
        return None
    return CompleteRun(number, runs[drop.run])


def piece_at(site: Site) -> Piece | None:
    """The piece of a function in ``site``'s file at its line and column, as the file reads now;
    None when it does not read or parse, or holds none there."""
    found = statement_at(site)
    return None if found is None else found[1]


def run_again(run: Running, numbers: Iterable[int], target: Target) -> None:
    """Run again each input ``numbers`` names, by its number in the run, from 1, once, in run
    order, labeled ``summary``, with no plan: the inputs a moment's formulas were checked on, so
    that each formula in use gives the solver its forks. Stops once one meets a stop."""
    checks = argument_checks(target)
    for number in sorted(set(numbers)):
        args = run.records[number - 1].args
        if isinstance(run.run_input(Seed.of(args, checks, target.home), Source.SUMMARY), Stop):
            return
