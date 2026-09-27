"""A list cut again and again at clamps the input's own values settle: the settled program first,
the unsettled one after a settled unsat, and that one given up past the steps its reads share."""

import time
from typing import Any

import pytest

from pyct.binding.bind import Seed, bind
from pyct.binding.model import apply
from pyct.core.branch import Branch, SinkItem
from pyct.solver import cvc5 as cvc5_module
from pyct.solver.answer import Sat, Unknown
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
        # ten cuts' reads fit the steps the 10 s default gives the unsettled program's reads
        (10, 10.0, 10.0),
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


@needs_cvc5
@pytest.mark.parametrize("times", [11, 12])
def test_an_unsettled_program_past_its_shared_steps_is_given_up_at_once(
    monkeypatch: pytest.MonkeyPatch, times: int
) -> None:
    # eleven cuts or more double the reads past what the 10 s default gives them: an unknown,
    # long before the limit, with cvc5 asked only about the settled program
    seed, path = _cut(times)
    asks: list[str] = []
    ask = cvc5_module._ask

    def counted(written: Program, timeout: float) -> Any:
        asks.append(written.text)
        return ask(written, timeout)

    monkeypatch.setattr(cvc5_module, "_ask", counted)

    started = time.perf_counter()
    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    assert answer == Unknown()
    assert len(asks) == 1
    # about 0.2 s alone; the margin is for a loaded machine, far inside the 10 s limit
    assert time.perf_counter() - started < 2.0
