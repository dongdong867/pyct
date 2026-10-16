"""Each program pyct gives cvc5 is kept while a caller takes them, and written as a file cvc5
runs as pyct did."""

import subprocess
from pathlib import Path

from pyct.core.branch import Branch, Site
from pyct.solver.answer import Error, Sat, Timeout, Unknown, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.given import Given, said, taking, took, write

SITE = Site(file="t.py", line=2, col=7)


def test_a_program_is_kept_only_while_a_caller_takes_them() -> None:
    program = Given("(check-sat)\n", (), "sat", 0.5)

    took(program)
    with taking() as programs:
        took(program)
        with taking() as inner:
            took(program)
    took(program)

    assert programs == [program]
    assert inner == [program]


def test_solve_keeps_each_program_it_gives_cvc5() -> None:
    fork = Branch(expression=[">", "x", 0], taken=False, site=SITE)

    with taking() as programs:
        answer = solve((fork,), {"x": int}, 10.0)

    assert isinstance(answer, Sat)
    (program,) = programs
    assert program.answer == "sat"
    assert program.seconds >= 0
    assert "(check-sat)" in program.text
    # cvc5 gets what is left of the limit once the program is written
    assert any(option.startswith("(set-option :tlimit-per ") for option in program.options)


def test_said_names_each_answer() -> None:
    assert [said(a) for a in (Sat({}), Unsat(), Unknown(), Timeout(), Error("x"))] == [
        "sat",
        "unsat",
        "unknown",
        "timeout",
        "error",
    ]


def test_write_numbers_an_ask_s_programs_and_cvc5_runs_each(tmp_path: Path) -> None:
    fork = Branch(expression=[">", "x", 0], taken=False, site=SITE)
    with taking() as programs:
        solve((fork,), {"x": int}, 10.0)
    second = Given("(set-logic ALL)\n(check-sat)\n", programs[0].options, "sat", 0.25)

    write(tmp_path, 3, "aim t.py:2:7 at position 0", [programs[0], second])

    assert sorted(path.name for path in tmp_path.iterdir()) == ["ask-3-2.smt2", "ask-3.smt2"]
    text = (tmp_path / "ask-3-2.smt2").read_text()
    assert text.splitlines()[:2] == [
        "; aim t.py:2:7 at position 0",
        "; cvc5 answered sat in 0.250 s",
    ]
    for name in ("ask-3.smt2", "ask-3-2.smt2"):
        ran = subprocess.run(["cvc5", str(tmp_path / name)], capture_output=True, text=True)
        assert ran.stdout.splitlines()[0] == "sat", ran
