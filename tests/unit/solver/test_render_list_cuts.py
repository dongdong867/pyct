"""A list cut again and again at clamps the input's own values settle: the settled program first,
the unsettled one after a settled unsat, and that one given up past the steps its reads share."""

import time
from typing import Any

import pytest

from pyct.binding.bind import Seed, bind
from pyct.binding.model import apply
from pyct.core.foundation.branch import Branch, SinkItem
from pyct.solver import cvc5 as cvc5_module
from pyct.solver.answer import Sat, Unknown, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.declared import Program
from tests.unit.solver.agreement import needs_cvc5


def _cut(times: int) -> tuple[Seed, tuple[Branch, ...]]:
    """``items[1:2] = [n]`` ``times`` times on ``[5]``, then ``items[-1] == 99`` flipped: only a
    list of three items or more ends in 99, which the clamps settled as the input had them rule
    out, so only the unsettled program answers."""
    args: dict[str, object] = {"items": [5]}
    sink: list[SinkItem] = []
    items: Any = bind(args, sink)["items"]
    for value in range(times):
        items[1:2] = [value]
    bool(items[-1] == 99)
    *forks, last = [item for item in sink if isinstance(item, Branch)]
    return Seed.of(args), (*forks, Branch(last.expression, not last.taken, last.site))


@needs_cvc5
@pytest.mark.serial
@pytest.mark.parametrize(
    ("times", "limit", "spent"),
    [
        # a read through six cuts runs past the steps a 5 s solve gives one read, so the settled
        # program answers unsat, then the unsettled one answers
        (6, 5.0, 2.0),
        # each cut's reads fit the steps the limit gives the unsettled program's reads, and
        # cvc5 answers them well inside it: seven cuts in 1 s, and nine in the 10 s default
        (7, 1.0, 1.0),
        (9, 10.0, 10.0),
    ],
)
def test_a_list_cut_past_what_the_input_held_is_solved_unsettled(
    times: int, limit: float, spent: float
) -> None:
    seed, path = _cut(times)

    started = time.perf_counter()
    answer = solve(path, seed.leaves, limit, seed.lists, seed.values)

    assert isinstance(answer, Sat), answer
    assert time.perf_counter() - started < spent
    solved: Any = apply(seed, answer.model).args
    assert len(solved["items"]) >= 3 and solved["items"][-1] == 99


@pytest.mark.parametrize(
    ("times", "limit", "asked"),
    [
        (8, 1.0, True),
        (9, 1.0, False),
        (8, 2.0, True),
        (9, 2.0, False),
        (9, 5.0, True),
        (10, 5.0, False),
        (9, 10.0, True),
        (10, 10.0, False),
    ],
)
def test_the_unsettled_program_is_asked_where_its_steps_fit_the_limit(
    monkeypatch: pytest.MonkeyPatch, times: int, limit: float, asked: bool
) -> None:
    # the steps a limit allows grow with its square root: eight cuts fit 1 s and 2 s, nine fit
    # 5 s and 10 s, and one cut more is given up. cvc5 is not run: the settled programs answer
    # unsat, and the unsettled one, written only where its steps fit, sat
    unsettled: list[Program] = []

    def answered(written: Program, timeout: float) -> Any:
        if written.narrowed:
            return Unsat(), frozenset()
        unsettled.append(written)
        return Sat({}), frozenset()

    monkeypatch.setattr(cvc5_module, "_ask", answered)
    seed, path = _cut(times)

    answer = solve(path, seed.leaves, limit, seed.lists, seed.values)

    assert (answer, len(unsettled)) == ((Sat({}), 1) if asked else (Unknown(), 0))


@needs_cvc5
@pytest.mark.parametrize(("times", "limit"), [(9, 2.0), (10, 10.0), (11, 10.0)])
def test_an_unsettled_program_past_its_shared_steps_is_given_up_at_once(
    monkeypatch: pytest.MonkeyPatch, times: int, limit: float
) -> None:
    # nine cuts double the reads past what a 2 s limit gives them, and ten past the 10 s
    # default: an unknown, long before the limit, with cvc5 asked only about the settled
    # program, and for its core
    seed, path = _cut(times)
    asks: list[str] = []
    ask = cvc5_module._ask

    def counted(written: Program, timeout: float) -> Any:
        asks.append(written.text)
        return ask(written, timeout)

    monkeypatch.setattr(cvc5_module, "_ask", counted)

    started = time.perf_counter()
    answer = solve(path, seed.leaves, limit, seed.lists, seed.values)

    assert answer == Unknown()
    # the settled program held the list's length small, so its unsat asks for the core
    settled, cored = asks
    assert ":named size!" not in settled
    assert cored.startswith("(set-option :dump-unsat-cores true)\n") and ":named size!" in cored
    # about 0.2 s alone; the margin is for a loaded machine, inside the limit
    assert time.perf_counter() - started < min(2.0, limit)
