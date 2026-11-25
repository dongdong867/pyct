"""The loss sites summaries ask about, each as soon as an input recorded a run of it, and what an
ask about one holds. Decision llm-summaries-ask-about-a-piece-once-an-input-recorded-a-run-of-it.

A loss site is the site of an operation pyct has not taught, a `math` call it does not follow, or
a watched call that lost a tracked value, whose runs an input recorded with summaries switched
on (`pyct.core.entry.losses`). The summaries tool hears each input the run keeps and notes each
site whose first recorded run the input holds, in the order the input recorded them, under the
name of the first downgrade recorded there (``LossSites``). Before each pass picks a fork, and
before the run would stop on ``no fork to flip``, the tool asks about each noted site that had
no turn this run, one at a time, in the order noted (`pyct.run.call_turns`); each site has one
turn per run, whatever came of it, and one more each time an input drops its formula in use.
An ask after a drop holds the dropped formula among the earlier tries, with why, and shows the
run it failed on first.

A site is skipped with no ask when Python converts its answer to a plain int or bool before the
target sees it (``CONVERTS``), or when an answer it recorded is no int, float, str or bool. Its
ask shows its runs as `pyct.run.summary_runs` picks them, each with its values going in named as
the code writes them (`pyct.results.losses`) and its answer under ``answer``, and its code is the
function that holds it, the site's lines marked
``# >>> the call`` and ``# <<< the call``, then the functions it calls in the target's package,
then, for a watched call whose callee is a Python function whose file reads, the callee's
source, while the code stays within ``CODE_LIMIT``; any other callee is named by its module
and qualified name.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field

from pyct.core.entry.losses import ANSWER
from pyct.core.foundation.branch import (
    Callee,
    Changed,
    FormulaDrop,
    GoingIn,
    LossKind,
    LossRun,
    Site,
)
from pyct.results.losses import loss_code
from pyct.results.record import InputRecord
from pyct.results.source_files import SourceFiles
from pyct.run.code_context import CODE_LIMIT, code_with_piece, function_code
from pyct.run.summary_asks import CallAsk, SummaryRequest
from pyct.run.summary_checks import AskedRun, CompleteRun
from pyct.run.summary_outcomes import SiteState
from pyct.run.summary_runs import not_shown, shown_runs
from pyct.run.target import Target

# the operations whose answer Python turns into a plain int or bool itself, so a tracked answer
# from a formula would never reach the target
CONVERTS = frozenset(
    {"__len__", "__contains__", "__bool__", "__index__", "__int__", "__float__", "__hash__"}
)
# why a site whose answer Python converts gets no ask
CONVERTED = "Python converts its answer"
# the word that marks a loss site in the code its ask sends
CALL = "call"
# the one name a loss site's formula gives a value
CHANGED = (ANSWER,)
# the answers a formula can stand for
ANSWERS = (int, float, str, bool)


@dataclass
class LossSites:
    """The loss sites the run's inputs recorded runs of, in the order first recorded, each by the
    name of the first downgrade recorded there, and those that had their turn this run."""

    names: dict[Site, str] = field(default_factory=dict)
    turned: set[Site] = field(default_factory=set)

    def heard(self, record: InputRecord) -> None:
        """Note each site whose first recorded run the input holds."""
        for run in record.losses:
            self.names.setdefault(run.site, run.name)

    def waiting(self) -> list[Site]:
        """The noted sites that had no turn this run, in the order noted."""
        return [site for site in self.names if site not in self.turned]


@dataclass(frozen=True)
class AskedCall:
    """A loss site as an ask sees it: its site, its complete runs, oldest first, the formula's
    parameters, the first and last line of its code, the downgrade's name and kind, the site's
    code as written, the latest run's callee, the first run's answer as recorded, and each value
    going in's parameter by its position, None for a constant."""

    site: Site
    runs: tuple[CompleteRun, ...]
    parameters: tuple[str, ...]
    lines: tuple[int, int]
    name: str
    kind: LossKind
    written: str
    callee: Callee | None
    answer: object
    positions: tuple[str | None, ...]


def asked_call(
    site: Site, name: str, records: Sequence[InputRecord], files: SourceFiles
) -> AskedCall | None:
    """The loss site at ``site`` whose downgrade is ``name``, with its runs in the records, oldest
    first, its code read through the run's ``files``; None when no run of it is recorded."""
    runs = [
        (number, each)
        for number, record in enumerate(records, start=1)
        for each in record.losses
        if each.site == site and each.name == name
    ]
    if not runs:
        return None
    first = runs[0][1]
    code = loss_code(site, name, first.kind, len(first.going_in), files)
    parameters = tuple(each for each in code.names if each is not None)
    complete = tuple(
        CompleteRun(number, _asked_run(each, code.names))
        for number, each in runs
        if len(each.going_in) == len(code.names)
    )
    callee = runs[-1][1].callee
    answer = json.loads(_answer(first))
    return AskedCall(
        site,
        complete,
        parameters,
        code.lines,
        name,
        first.kind,
        code.written,
        callee,
        answer,
        code.names,
    )


def _asked_run(run: LossRun, names: tuple[str | None, ...]) -> AskedRun:
    """A loss run as an ask sees it: each value going in under its parameter's name, the
    constants left out, and its answer."""
    going_in = tuple(
        GoingIn(name, each.value, each.tracked)
        for name, each in zip(names, run.going_in, strict=True)
        if name is not None
    )
    return AskedRun(going_in, (Changed(ANSWER, _answer(run)),))


def _answer(run: LossRun) -> str:
    return run.changed[0].value


def failed_call_run(
    drop: FormulaDrop, record: InputRecord, number: int, files: SourceFiles
) -> CompleteRun | None:
    """The run of the loss site an input's drop names by its position, as the input's record
    holds it and as the site's ask shows it, the input numbered ``number``. None when the drop
    names no run, the record holds none there, or its values do not fit the site's code."""
    runs = [each for each in record.losses if each.site == drop.site]
    if drop.run is None or not 0 <= drop.run < len(runs):
        return None
    run = runs[drop.run]
    code = loss_code(run.site, run.name, run.kind, len(run.going_in), files)
    if len(run.going_in) != len(code.names):
        return None
    return CompleteRun(number, _asked_run(run, code.names))


def skipped_because(call: AskedCall) -> str | None:
    """Why a loss site gets no ask, or None when it gets one: Python converts its answer, or no
    run of it is complete, or the answer it recorded is not an int, float, str or bool."""
    if call.name in CONVERTS:
        return CONVERTED
    if not call.runs:
        return "no recorded run"
    answer = call.answer
    if isinstance(answer, ANSWERS):
        return None
    return "the answer is None" if answer is None else f"the answer is a {type(answer).__name__}"


def call_request(
    target: Target,
    call: AskedCall,
    place: str,
    files: SourceFiles,
    state: SiteState | None = None,
) -> SummaryRequest:
    """The ask about a loss site, at its ``place``, its code read through the run's ``files``,
    with the earlier tries its ``state`` keeps, and the run its last formula was dropped on first
    among the runs shown."""
    code = code_with_piece(target, call.site.file, call.lines, CALL, files)
    callee, source = _callee(call.callee, CODE_LIMIT - len(code) - 2, files)
    if source is not None:
        code = f"{code}\n\n{source}" if code else source
    shown = shown_runs(call, None if state is None else state.failed_on)
    return SummaryRequest(
        place=place,
        code=code,
        parameters=call.parameters,
        changed=CHANGED,
        runs=shown,
        call=CallAsk(call.name, call.written, callee, source is not None),
        tries=() if state is None else tuple(state.tries),
        not_shown=not_shown(call, shown),
    )


def _callee(callee: Callee | None, room: int, files: SourceFiles) -> tuple[str | None, str | None]:
    """A callee's module and qualified name, and its source when it is a Python function whose
    file reads and whose source fits in ``room``; Nones for no callee."""
    if callee is None:
        return None, None
    named = f"{callee.module}.{callee.qualname}"
    if callee.file is None or callee.line is None:
        return named, None
    source = function_code(callee.file, callee.line, named, files)
    return named, source if source is not None and len(source) <= room else None
