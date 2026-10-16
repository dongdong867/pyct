"""How pyct gives cvc5 a program: the command, each program kept while an ask runs, and the
file that runs it again.

An ask is one fork pyct asks the solver to flip, with every program it
writes for it. While a caller holds ``taking``, each program ``cvc5`` runs
is kept with what cvc5 answered and how long it took; ``write`` puts one
ask's programs in a folder, ``ask-<n>.smt2`` for its first and
``ask-<n>-<k>.smt2`` for its k-th, each headed by comments and the options
pyct gave cvc5 on its command line, so ``cvc5 <file>`` runs it as pyct did.
"""

from __future__ import annotations

import contextlib
import math
from collections.abc import Generator, Sequence
from dataclasses import dataclass
from pathlib import Path

from pyct.solver.answer import Answer, Sat, Timeout, Unknown, Unsat
from pyct.solver.answer_size import MOST_ITEMS
from pyct.solver.locate import locate

# read one SMT-LIB program from stdin, print a model with the answer, say nothing else, and
# write each string in the model in full, up to the longest an answer holds
ARGUMENTS = (
    "--produce-models",
    "--lang",
    "smt",
    "--quiet",
    f"--strings-model-max-len={MOST_ITEMS}",
)

# the programs of each ask a caller is taking now, the innermost last
_TAKING: list[list[Given]] = []


@dataclass(frozen=True)
class Given:
    """One program pyct gave cvc5: its text, the options it ran under as SMT-LIB commands, what
    cvc5 answered (``sat``, ``unsat``, ``unknown``, ``timeout`` or ``error``) and the seconds it
    took."""

    text: str
    options: tuple[str, ...]
    answer: str
    seconds: float


@contextlib.contextmanager
def taking() -> Generator[list[Given]]:
    """Every program cvc5 runs inside the block, in order, kept in the list it yields."""
    programs: list[Given] = []
    _TAKING.append(programs)
    try:
        yield programs
    finally:
        _TAKING.pop()


def took(program: Given) -> None:
    """Keep a program cvc5 ran, when a caller is taking them."""
    if _TAKING:
        _TAKING[-1].append(program)


def write(folder: Path, number: int, about: str, programs: Sequence[Given]) -> None:
    """Write the n-th ask's programs into ``folder``, each headed by ``about`` and its answer."""
    for k, program in enumerate(programs, start=1):
        name = f"ask-{number}.smt2" if k == 1 else f"ask-{number}-{k}.smt2"
        head = [f"; {about}", f"; cvc5 answered {program.answer} in {program.seconds:.3f} s"]
        lines = [*head, *program.options]
        (folder / name).write_text("\n".join(lines) + "\n" + program.text, encoding="utf-8")


def argv(timeout: float) -> list[str]:
    """The command. cvc5 counts its limit in milliseconds, and rounds up is the honest way.

    The limit is on the check, ``--tlimit-per``, where cvc5 answers
    ``unknown`` and exits. ``--tlimit`` would end the whole process with
    ``abort()``, which the system records as a crash. Rounding up also keeps
    any limit above zero at 1 or more, since cvc5 reads ``--tlimit-per=0``
    as no limit.
    """
    return [str(locate()), *ARGUMENTS, f"--tlimit-per={_milliseconds(timeout)}"]


def options(timeout: float) -> tuple[str, ...]:
    """The options ``argv`` gives cvc5, as the SMT-LIB commands a file sets them with."""
    return (
        "(set-option :produce-models true)",
        f"(set-option :strings-model-max-len {MOST_ITEMS})",
        f"(set-option :tlimit-per {_milliseconds(timeout)})",
    )


def said(answer: Answer) -> str:
    """The answer in cvc5's word, or ``timeout`` and ``error`` for the two pyct names."""
    words: dict[type, str] = {Sat: "sat", Unsat: "unsat", Unknown: "unknown", Timeout: "timeout"}
    return words.get(type(answer), "error")


def _milliseconds(timeout: float) -> int:
    """The limit in cvc5's milliseconds, rounded up."""
    return math.ceil(timeout * 1000)
