"""The loss sites summaries ask about, each as soon as an input recorded a run of it, and what an
ask about one holds. Decision llm-summaries-ask-about-a-piece-once-an-input-recorded-a-run-of-it.

A loss site is the site of an operation pyct has not taught, a `math` call it does not follow, or
a watched call that lost a tracked value, whose runs an input recorded with summaries switched
on (`pyct.core.entry.losses`). The summaries tool hears each input the run keeps and notes each
site whose first recorded run the input holds, in the order the input recorded them, under the
name of the first downgrade recorded there (``LossSites``). Before each pass picks a fork, and
before the run would stop on ``no fork to flip``, the tool asks about each noted site that had
no turn this run, one at a time, in the order noted (`pyct.run.summaries.Summaries.between`);
each site has one turn per run, whatever came of it.

A site is skipped with no ask when Python converts its answer to a plain int or bool before the
target sees it (``CONVERTS``), or when an answer it recorded is no int, float, str or bool. Its
ask is a loop's ask (`pyct.run.summary_runs`) about the site as a piece that changes ``answer``:
its complete runs are its recorded runs, the values going in named as the code writes them
(`pyct.results.losses`), and its code is the function that holds it, the site's lines marked
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
from pyct.core.foundation.branch import Callee, Changed, GoingIn, LossKind, LossRun, PieceRun, Site
from pyct.results.losses import loss_code
from pyct.results.pieces import Piece
from pyct.results.record import InputRecord
from pyct.results.source_files import SourceFiles
from pyct.run.code_context import CODE_LIMIT, code_with_piece, function_code
from pyct.run.summary_asks import CallAsk, EarlierFormula, SummaryRequest
from pyct.run.summary_checks import CompleteRun
from pyct.run.summary_runs import AskedLoop, not_shown, shown_runs
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
# the answers a formula can stand for
_ANSWERS = (int, float, str, bool)


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
    """A loss site as an ask sees it: as a piece that changes ``answer``, with its complete runs
    and its parameters (``AskedLoop``), the downgrade's name and kind, the site's code as
    written, the latest run's callee, each run's first answer as recorded, and each value going
    in's parameter by its position, None for a constant."""

    loop: AskedLoop
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
        CompleteRun(number, _as_piece_run(each, code.names))
        for number, each in runs
        if len(each.going_in) == len(code.names)
    )
    piece = Piece(site.line, site.col, parameters, (ANSWER,), code.lines)
    loop = AskedLoop(site, piece, complete, parameters)
    callee = runs[-1][1].callee
    answer = json.loads(_answer(first))
    return AskedCall(loop, name, first.kind, code.written, callee, answer, code.names)


def _as_piece_run(run: LossRun, names: tuple[str | None, ...]) -> PieceRun:
    """A loss run as a piece's run: each value going in under its parameter's name, the
    constants left out, and its answer."""
    going_in = tuple(
        GoingIn(name, each.value, each.tracked)
        for name, each in zip(names, run.going_in, strict=True)
        if name is not None
    )
    return PieceRun(run.site, going_in, (Changed(ANSWER, _answer(run)),))


def _answer(run: LossRun) -> str:
    return run.changed[0].value


def skipped_because(call: AskedCall) -> str | None:
    """Why a loss site gets no ask, or None when it gets one: Python converts its answer, or no
    run of it is complete, or the answer it recorded is not an int, float, str or bool."""
    if call.name in CONVERTS:
        return CONVERTED
    if not call.loop.runs:
        return "no recorded run"
    answer = call.answer
    if isinstance(answer, _ANSWERS):
        return None
    return "the answer is None" if answer is None else f"the answer is a {type(answer).__name__}"


def call_request(
    target: Target,
    call: AskedCall,
    place: str,
    tries: tuple[EarlierFormula, ...],
    files: SourceFiles,
) -> SummaryRequest:
    """The ask about a loss site, at its ``place``, with its earlier tries, its code read through
    the run's ``files``."""
    loop = call.loop
    code = code_with_piece(target, loop.site.file, loop.piece.lines, CALL, files)
    callee, source = _callee(call.callee, CODE_LIMIT - len(code) - 2, files)
    if source is not None:
        code = f"{code}\n\n{source}" if code else source
    shown = shown_runs(loop)
    return SummaryRequest(
        place=place,
        code=code,
        parameters=loop.parameters,
        changed=loop.piece.changed,
        runs=shown,
        tries=tries,
        not_shown=not_shown(loop, shown),
        call=CallAsk(call.name, call.written, callee, source is not None),
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
