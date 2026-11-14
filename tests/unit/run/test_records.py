"""An input's record holds what its call did, the recorded runs of its pieces among it."""

from pyct.core.foundation.branch import Changed, GoingIn, PieceRun, Site
from pyct.execution.execute import ExecutionResult
from pyct.results.record import InputRecord
from pyct.run.records import record_of

RUN = PieceRun(
    site=Site(file="m.py", line=3, col=4),
    going_in=(GoingIn("n", "2", tracked=True),),
    changed=(Changed("i", "2"),),
)


def test_a_record_holds_the_recorded_runs_of_its_call_s_pieces() -> None:
    executed = ExecutionResult(lines=frozenset({3}), branches=(), pieces=(RUN,))

    record = record_of({"n": 2}, executed)

    assert record.pieces == (RUN,)
    assert InputRecord(args={}, forks=(), covered_lines=frozenset()).pieces == ()
