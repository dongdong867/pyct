"""Acceptance tests for the track-a-value-through-a-loop-summary story through ``run()``: once a
loop's formula passes its checks it comes into use, each later input runs the loop on plain
values, and the loop's changed values after it hold the formula's terms, which the solver can aim
at.

Each run has summaries on with a fake provider, its package intercepted with the recording of
each loop's runs, and each input in a forked child; no test calls a model.
"""

import json
from collections.abc import Sequence
from pathlib import Path

from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.core.foundation.branch import Branch
from pyct.results.jsonl import render_summary
from pyct.results.llm_asks import LlmUse
from pyct.results.record import InputRecord, Source
from pyct.run.isolation import Isolation
from tests.acceptance.llm_summaries import (
    COUNT,
    ONE_MOMENT,
    SEED,
    FakeSummaries,
    G,
    Summarized,
    code_reply,
    one_thread,  # noqa: F401
    run_summaries,
)
from tests.acceptance.test_substitute_is_and_in import plain_lines

LOOPS = "targets.summaries.loops"
# the count of "z" in s as a fork's expression writes it, after a loop that starts from 0
Z = ["+", 0, ["count", "s", "'z'"]]
CAPPED = code_reply(
    "def summary(s, t):\n"
    '    t = t + s.count("z")\n'
    "    if t > 5:\n"
    "        t = 5\n"
    '    return {"t": t}'
)
# a run that goes on well past its first moment
LONGER = Limits(plateau=Plateau(20))


def line_of(function: str, code: str) -> int:
    """The line of G, inside ``function``, that reads ``code`` once stripped."""
    lines = Path(G).read_text(encoding="utf-8").splitlines()
    start = lines.index(f"def {function}(s: str) -> str:")
    return next(at for at in range(start, len(lines)) if lines[at].strip() == code) + 1


def loop_lines(function: str, first: str, last: str) -> range:
    """The lines of ``function``'s loop, from the line that reads ``first`` to ``last``'s."""
    return range(line_of(function, first), line_of(function, last) + 1)


def after_checked(done: Summarized) -> list[InputRecord]:
    """The inputs that ran after the formula's ``checked on`` line."""
    checked = next(at for at, line in enumerate(done.said) if ": checked on " in line)
    before = sum(1 for line in done.said[:checked] if line.startswith("input "))
    return done.records[before:]


def before_checked(done: Summarized) -> list[InputRecord]:
    after = after_checked(done)
    return done.records[: len(done.records) - len(after)]


def forks_at(record: InputRecord, line: int) -> list[Branch]:
    return [each for each in record.forks if each.site.line == line]


def holds(expression: object, part: object) -> bool:
    """Whether the expression is ``part`` or holds it at any depth."""
    if expression == part:
        return True
    return isinstance(expression, list) and any(holds(each, part) for each in expression)


def summarized(
    function: str,
    reply: str,
    limits: Limits = ONE_MOMENT,
    isolation: Isolation = Isolation.AUTO,
) -> Summarized:
    """``function`` of G run from the seed, the provider answering ``reply``, past the formula's
    ``checked on`` line, each input where ``isolation`` says."""
    spec = f"{LOOPS}::{function}"
    provider = FakeSummaries([reply])
    done = run_summaries(spec, SEED, provider, limits, isolation)
    assert len(provider.requests) == 1
    assert after_checked(done), done.said
    return done


def every_after_holds(records: Sequence[InputRecord], line: int, expression: object) -> None:
    for record in records:
        assert [each.expression for each in forks_at(record, line)] == [expression], record


# llm-summary-for-a-stuck-loop-in-use-tracks-the-changed-value
def test_an_input_after_the_check_forks_on_the_formula_s_count() -> None:
    done = summarized("few_z", COUNT)

    every_after_holds(after_checked(done), line_of("few_z", "if t > 3:"), [">", Z, 3])


# llm-summary-for-a-stuck-loop-in-use-in-a-fresh-interpreter
def test_an_input_in_a_fresh_interpreter_forks_on_the_formula_s_count() -> None:
    done = summarized("few_z", COUNT, isolation=Isolation.FRESH)

    every_after_holds(after_checked(done), line_of("few_z", "if t > 3:"), [">", Z, 3])
    # inputs that start fresh run in a process of their own, so the formula is in use
    assert not any(" not used: " in line for line in done.llm_said())
    assert state_of(done) == "in use"


# llm-summary-for-a-stuck-loop-in-use-loop-records-no-fork
def test_an_input_after_the_check_records_no_fork_in_the_loop() -> None:
    done = summarized("few_z", COUNT)

    loop = loop_lines("few_z", "for c in s:", "t += 1")
    test = line_of("few_z", 'if c == "z":')
    for record in before_checked(done):
        s = record.args["s"]
        assert isinstance(s, str)
        assert len(forks_at(record, test)) == len(s), record
    for record in after_checked(done):
        assert [each for each in record.forks if each.site.line in loop] == [], record


# llm-summary-for-a-stuck-loop-in-use-reaches-the-missed-line, its input labeled `summary` as
# label-the-inputs-a-summary-gave's llm-summary-input-solver-aimed-at-the-formula says
def test_the_solver_aims_at_the_formula_s_count_and_covers_the_missed_line() -> None:
    done = summarized("few_z", COUNT, LONGER)

    many = line_of("few_z", 'return "many"')
    reached = [
        record
        for record in after_checked(done)
        if str(record.args["s"]).count("z") >= 4 and record.source is Source.SUMMARY
    ]
    assert reached, [record.args for record in after_checked(done)]
    assert many in reached[0].covered_lines
    assert many in done.result.coverage.covered[G]


# llm-summary-for-a-stuck-loop-in-use-while
def test_a_while_loop_in_use_forks_on_the_count_after_it_and_not_inside() -> None:
    reply = code_reply('def summary(s, t, i):\n    return {"t": t + s.count("z")}')

    done = summarized("few_while", reply)

    after = after_checked(done)
    every_after_holds(after, line_of("few_while", "if t > 3:"), [">", Z, 3])
    loop = loop_lines("few_while", "while i < len(s):", "i += 1")
    for record in after:
        assert [each for each in record.forks if each.site.line in loop] == [], record


# llm-summary-for-a-stuck-loop-in-use-comprehension
def test_a_comprehension_in_use_forks_on_the_count_after_it_and_not_at_its_line() -> None:
    reply = code_reply('def summary(s):\n    return {"t": s.count("z")}')

    done = summarized("few_counted", reply)

    after = after_checked(done)
    expression = [">", ["count", "s", "'z'"], 3]
    every_after_holds(after, line_of("few_counted", "if t > 3:"), expression)
    comprehension = line_of("few_counted", 't = sum(1 for c in s if c == "z")')
    for record in after:
        assert forks_at(record, comprehension) == [], record


# llm-summary-for-a-stuck-loop-in-use-each-changed-value
def test_each_changed_value_of_a_loop_in_use_holds_its_own_count() -> None:
    reply = code_reply(
        "def summary(s, ups, downs):\n"
        '    return {"ups": ups + s.count("u"), "downs": downs + s.count("d")}'
    )

    done = summarized("few_tallies", reply)

    ups, downs = line_of("few_tallies", "if ups > 3:"), line_of("few_tallies", "if downs > 3:")
    after = [record for record in after_checked(done) if forks_at(record, downs)]
    assert after
    for record in after:
        [up] = forks_at(record, ups)
        [down] = forks_at(record, downs)
        assert holds(up.expression, ["count", "s", "'u'"]), up
        assert holds(down.expression, ["count", "s", "'d'"]), down


# llm-summary-for-a-stuck-loop-in-use-formula-if-forks-at-the-loop
def test_the_formula_s_own_if_forks_at_the_loop_s_line() -> None:
    done = summarized("capped", CAPPED)

    loop, four = line_of("capped", "for c in s:"), line_of("capped", "if t == 4:")
    after = [record for record in after_checked(done) if str(record.args["s"]).count("z") <= 5]
    assert after
    for record in after:
        lines = [each.site.line for each in record.forks]
        [formula] = forks_at(record, loop)
        assert (formula.expression, formula.taken) == ([">", Z, 5], False), record
        assert lines.index(loop) < lines.index(four), record


# llm-summary-for-a-stuck-loop-in-use-state
def test_a_formula_in_use_is_listed_in_use() -> None:
    done = summarized("few_z", COUNT)

    assert state_of(done) == "in use"


# llm-summary-for-a-stuck-loop-not-used-for-a-loop-that-can-leave
def test_a_formula_for_a_loop_that_returns_is_not_used_and_says_why() -> None:
    done = summarized("few_stops", COUNT)

    loop = line_of("few_stops", "for c in s:")
    said = done.llm_said()
    checked = next(at for at, line in enumerate(said) if ": checked on " in line)
    not_used = f"llm: summary for the loop at {G}:{loop} not used: the loop holds a return"
    assert said[checked + 1] == not_used
    assert said.count(not_used) == 1
    stop, z = line_of("few_stops", 'if c == "!":'), line_of("few_stops", 'if c == "z":')
    for record in after_checked(done):
        s = str(record.args["s"])
        read = s.index("!") + 1 if "!" in s else len(s)
        # each character read forks at the `"!"` test, and each but a `"!"` at the `"z"` test
        assert len(forks_at(record, stop)) == read, record
        assert len(forks_at(record, z)) == len(s[:read].replace("!", "")), record
        assert not any(holds(each.expression, Z) for each in record.forks), record
    assert state_of(done) == "checked"


def state_of(done: Summarized) -> object:
    """The state of the run's one loop in the summary line's ``llm.summaries``."""
    use = LlmUse("openai:gpt-6-luna", ("summaries",))
    [item] = json.loads(render_summary(done.result, use))["llm"]["summaries"]
    return item["state"]


# llm-summary-for-a-stuck-loop-in-use-a-raise-leaves-the-input-plain
def test_a_raise_in_a_loop_in_use_leaves_the_input_s_values_plain() -> None:
    done = summarized("guarded", COUNT)

    starts = line_of("guarded", 'if s.startswith("#"):')
    assert any(forks_at(record, starts) for record in before_checked(done))
    hashed = [record for record in after_checked(done) if "#" in str(record.args["s"])]
    assert hashed, [record.args for record in after_checked(done)]
    for record in hashed:
        plain = plain_lines(Path(G), "guarded", record.args["s"])
        assert sorted(record.covered_lines) == plain, record
        assert forks_at(record, starts) == [], record
