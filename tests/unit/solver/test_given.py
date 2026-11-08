"""Each program pyct gives cvc5 is kept while a caller takes them, and written as a file cvc5
runs as pyct did."""

import subprocess
from pathlib import Path

import pytest

from pyct.core.foundation.branch import Branch, Expression, Site
from pyct.solver.answer import Error, Sat, Timeout, Unknown, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.given import ARGUMENTS, Given, answered, argv, options, taking, took, write
from pyct.solver.render import program

SITE = Site(file="t.py", line=2, col=7)

LEAVES: dict[str, type] = {"n": int, "x": float, "s": str}

# cvc5 1.4.2 answers a program that converts between a double and a real within the limit with
# these, the first kind where the program holds a string and the second where it does not
STRINGS_ADDED = {"--no-strings-lazy-pp": "(set-option :strings-lazy-pp false)"}
OTHERS_ADDED = {
    "--decision=internal": "(set-option :decision internal)",
    "--nl-cov": "(set-option :nl-cov true)",
}

# a path of each kind, and the options cvc5 gets for it beside today's
KINDS = [
    # a double read as a real
    pytest.param(["<", ["floor", "x"], "n"], OTHERS_ADDED, id="double-to-real"),
    # an int's real rounded to a double, which reads no double as a real
    pytest.param([">", ["+", "n", 0.5], "x"], OTHERS_ADDED, id="real-to-double"),
    # a string's digits rounded to a double
    pytest.param(["==", ["float", "s"], 100000.0], STRINGS_ADDED, id="string-to-double"),
    pytest.param([">", ["+", "n", 1], 0], {}, id="ints"),
    pytest.param([">", ["+", "x", 1.5], 0.0], {}, id="doubles"),
    pytest.param(["==", ["len", "s"], 3], {}, id="strings"),
    # a string that only spells a conversion, a quote inside it among them
    pytest.param(["==", "s", repr("(fp.to_real x)")], {}, id="spelled-to-real"),
    pytest.param(["==", "s", repr('say "((_ to_fp 11 53) RNE" now')], {}, id="spelled-to-double"),
]


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


def test_answered_is_cvc5_s_own_word_with_pyct_s_reading_when_it_differs() -> None:
    assert answered("sat\n(\n)\n", Sat({})) == "sat"
    assert answered("unsat\n", Unsat()) == "unsat"
    assert answered("unknown\n(:reason-unknown incomplete)\n", Unknown()) == "unknown"
    assert answered("unknown\n(:reason-unknown timeout)\n", Timeout()) == "unknown (timeout)"
    # a sat whose model pyct cannot read
    assert answered("sat\n(bad\n", Unknown()) == "sat (unknown)"
    assert answered("", Error("crashed")) == "no answer (error)"
    assert answered(None, Timeout()) == "no answer (timeout)"


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


def _text(expression: Expression) -> str:
    fork = Branch(expression=expression, taken=True, site=SITE)
    return program((fork,), LEAVES).text


@pytest.mark.parametrize(("expression", "added"), KINDS)
def test_cvc5_gets_options_by_what_the_program_converts(
    expression: Expression, added: dict[str, str]
) -> None:
    text = _text(expression)

    assert argv(2.5, text)[1:] == [*ARGUMENTS, "--tlimit-per=2500", *added]
    assert options(2.5, text) == (
        "(set-option :produce-models true)",
        "(set-option :strings-model-max-len 1000000)",
        "(set-option :tlimit-per 2500)",
        *added.values(),
    )


@pytest.mark.parametrize(("expression", "added"), KINDS)
def test_a_kept_program_s_option_lines_are_what_it_ran_with(
    expression: Expression, added: dict[str, str]
) -> None:
    fork = Branch(expression=expression, taken=False, site=SITE)
    with taking() as programs:
        solve((fork,), LEAVES, 10.0)

    assert programs
    for kept in programs:
        assert kept.options[3:] == tuple(added.values())


@pytest.mark.parametrize(
    ("expression", "said"),
    [
        (["<", ["floor", "x"], "n"], "internal\ntrue\ntrue\n"),
        (["==", ["float", "s"], 100000.0], "internal\ntrue\nfalse\n"),
    ],
)
def test_the_option_lines_set_what_the_command_line_does(
    tmp_path: Path, expression: Expression, said: str
) -> None:
    text = _text(expression)
    asked = ["(get-option :decision)", "(get-option :nl-cov)", "(get-option :strings-lazy-pp)"]
    query = "\n".join(["(set-logic ALL)", *asked]) + "\n"
    (tmp_path / "set.smt2").write_text("\n".join(options(10.0, text)) + "\n" + query)

    by_flags = subprocess.run(argv(10.0, text), input=query, capture_output=True, text=True)
    by_lines = subprocess.run(["cvc5", str(tmp_path / "set.smt2")], capture_output=True, text=True)

    # cvc5 reports decision and nl-cov at their defaults, internal and true, unless set, whatever
    # it then picks; an option it does not know is an error in its output
    assert by_lines.stdout == by_flags.stdout == said, (by_flags, by_lines)
