"""What cvc5 says back to an ask: its answer, and the holds an unsat's core names."""

from pyct.solver.answer import Answer, Error, Sat, Timeout, Unknown, Unsat, model_from
from pyct.solver.declared import Program
from pyct.solver.floats import FINITE
from pyct.solver.size_holds import SIZE
from pyct.solver.written_in import STAYS_NAME

# cvc5's reply to WHY when its time limit ended the check
OUT_OF_TIME = "(:reason-unknown timeout)"

# how cvc5's reply to WHY starts after an answer other than unknown, which has no reason
NO_REASON = "(error "


def core_of(stdout: str, written: Program) -> frozenset[str]:
    """The leaves, lists and dicts an unsat answer's dumped core holds finite, by their names,
    and the size holds and the values held where a result wrote them in it names, by theirs.

    cvc5 prints the core right after the answer, its assertion names on one
    line or one per line; every other line after an unsat is a refusal that
    names no assertion. Each name is ``FINITE`` and the leaf's symbol, or the symbol of the
    list or dict that holds the float and a count (``held_items``), or ``SIZE`` and a count
    (``size_holds``), or ``STAYS_NAME`` and a count (``written_in``).
    """
    words = stdout.replace("(", " ").replace(")", " ").split()
    names = {**written.names_by_symbol, **written.holders}
    named = [word.removeprefix(FINITE) for word in words if word.startswith(FINITE)]
    held = [word for word in words if word.startswith((SIZE, STAYS_NAME))]
    return frozenset(names[symbol.partition("!")[0]] for symbol in named) | frozenset(held)


def stayed(core: frozenset[str]) -> bool:
    """Whether an unsat's core names a value held where a result wrote it in, which no ask
    frees."""
    return any(name.startswith(STAYS_NAME) for name in core)


def answer_of(stdout: str, stderr: str) -> Answer:
    """What cvc5 said. The first word decides; anything unrecognized is kept whole.

    The last line is cvc5's reply to ``WHY``, so a model is the lines between
    the answer and that reply. A ``sat`` whose last line is not that reply is
    an ``Error``: the line dropped as the reply might have been a value.
    """
    lines = stdout.strip().splitlines()
    head = lines[0] if lines else ""
    if head == "sat" and lines[-1].startswith(NO_REASON):
        return Sat(model_from(lines[1:-1]))
    if head == "unsat":
        return Unsat()
    if head == "unknown":
        return Timeout() if lines[-1] == OUT_OF_TIME else Unknown()
    return Error(f"{stdout}\n{stderr}".strip())
