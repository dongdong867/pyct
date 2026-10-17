"""A run times each ask, hands each one out numbered with its programs, and marks the lines each
input covered first."""

from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.target import load_target
from pyct.run.tell import Ask, Tell

# line 2 `if x > 0:` flips sat; line 3 `if x < 0:` under it is unsat
NESTED = "targets.asks.sat_then_unsat::nested"


def test_each_ask_is_timed_and_handed_out_numbered_with_its_programs() -> None:
    asks: list[Ask] = []

    result = run(
        load_target(NESTED), {"x": 0}, isolation=Isolation.IN_PROCESS, tell=Tell(asked=asks.append)
    )

    seed, solved = result.records
    assert seed.solver_seconds is None
    assert solved.solver_seconds is not None and solved.solver_seconds > 0
    (miss,) = result.misses
    assert miss.solver_seconds > 0
    assert [ask.number for ask in asks] == [1, 2]
    assert [ask.path for ask in asks] == [0, 1]
    assert [ask.aim.site.line for ask in asks] == [2, 3]
    assert [[program.answer for program in ask.programs] for ask in asks] == [["sat"], ["unsat"]]
    sat, unsat = (sum(program.seconds for program in ask.programs) for ask in asks)
    assert sat <= solved.solver_seconds
    assert unsat <= miss.solver_seconds


def test_each_record_names_the_lines_it_covered_first() -> None:
    target = load_target(NESTED)

    result = run(target, {"x": 0}, isolation=Isolation.IN_PROCESS)

    seed, solved = result.records
    # line 1, the def, is the import's
    assert target.import_lines >= {1}
    assert seed.first_covered == {target.file: {2, 6}}
    assert solved.first_covered == {target.file: {3, 5}}
