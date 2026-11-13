"""Acceptance tests for the rewrite-what-the-solver-gives-up-on story: a failed try is asked
again with its reason, up to 3 times after the first ask, and a kept rewrite stands in for its
condition in later asks until one of its inputs takes the other side.

Each runs ``run()`` with a fake ``RewriteProvider`` that answers fixed text.
"""

import pytest

from pyct.core.foundation.branch import Site
from pyct.results.causes import Condition
from pyct.results.record import Source, StopKind
from pyct.rewrite.condition import rewrite_code
from pyct.rewrite.kept import Kept
from pyct.run import loop as loop_module
from pyct.run import rewrites as rewrites_module
from tests.acceptance.llm_rewrites import (
    FakeRewrites,
    file_of,
    llm_said,
    one_thread,  # noqa: F401
    run_rewrites,
)

TEXT = "targets.rewrites.text::exponent"
# `exponent(s, n)`: `if float(s) == 1e-30:` on line 2, then `if n > 0:` on line 3 guards
# `return 2` on line 4
COUNTED = "targets.rewrites.counted::exponent"
F = file_of("text")
AT = f"llm: rewrite for {F}:2:7"


def tries_said(said: list[str], at: str = AT) -> list[str]:
    """Each try line at ``at``, after its ``try N: ``... prefix up to the try's number."""
    return [line for line in llm_said(said) if line.startswith(f"{at}, try ")]


# llm-rewrite-retried-sends-the-input-that-took-the-other-side
def test_a_try_whose_input_took_the_other_side_is_asked_again_with_it() -> None:
    provider = FakeRewrites(['s == "1e-29"', 's == "1e-30"'])

    ran = run_rewrites(TEXT, {"s": "0"}, provider)

    assert tries_said(ran.said) == [f'{AT}, try 1: the input {{"s": "1e-29"}} took the other side']
    [earlier] = provider.requests[1].tries
    assert earlier.rewrite == 's == "1e-29"'
    assert '{"s": "1e-29"}' in earlier.reason
    assert llm_said(ran.said)[-1] == f"{AT}: took the wanted side"


# llm-rewrite-retried-sends-the-solver-s-answer
def test_a_try_the_solver_cannot_answer_is_asked_again_with_its_answer() -> None:
    provider = FakeRewrites(["float(s) == 1e-30", 's == "1e-30"'])

    ran = run_rewrites(TEXT, {"s": "0"}, provider)

    [line] = tries_said(ran.said)
    assert line in (
        f"{AT}, try 1: the solver answered unknown",
        f"{AT}, try 1: the solver answered timeout",
    )
    [earlier] = provider.requests[1].tries
    assert earlier.rewrite == "float(s) == 1e-30"
    assert earlier.reason == line.partition("try 1: ")[2]


# llm-rewrite-retried-stops-after-three
def test_a_condition_is_asked_about_4_times_at_most_at_a_moment() -> None:
    provider = FakeRewrites(['s == "1e-29"'])

    ran = run_rewrites(TEXT, {"s": "0"}, provider)

    numbers = [line.split(", try ")[1].partition(":")[0] for line in tries_said(ran.said)]
    assert numbers == ["1", "2", "3", "4"]
    assert len(provider.requests) == 4
    # the run goes on to its own stop once the tries' inputs joined the tree
    assert ran.result.stopped.kind is StopKind.NO_FORK


# llm-rewrite-retried-counts-a-reply-pyct-cannot-use
def test_a_reply_pyct_cannot_use_counts_as_a_try(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[object] = []
    solve = loop_module.solve

    def counted(held: tuple[object, ...], *args: object) -> object:
        # an ask that holds a fork of a rewrite's, whose file is the rewrite's
        files = [getattr(getattr(item, "site", None), "file", "") for item in held]
        if any(file.startswith("<rewrite") for file in files):
            asked.append(held)
        return solve(held, *args)  # pyrefly: ignore[bad-argument-type]

    monkeypatch.setattr(loop_module, "solve", counted)
    replies = ["n & 1 == 1", '__import__("os").getcwd() == s', "this is not code", "n == 3"]
    provider = FakeRewrites(replies)

    ran = run_rewrites(COUNTED, {"s": "0", "n": 0}, provider)

    at = f"llm: rewrite for {file_of('counted')}:2:7"
    assert tries_said(ran.said, at)[:3] == [
        f"{at}, try 1: pyct does not follow __and__",
        f"{at}, try 2: a rewrite may not call __import__",
        f"{at}, try 3: the reply holds no expression",
    ]
    assert len(provider.requests) == 4
    # only the fourth reply, which pyct can use, is asked of the solver
    assert len(asked) == 1


# llm-rewrite-input-reuses-a-kept-rewrite
def test_a_kept_rewrite_stands_in_for_its_condition_in_a_later_ask() -> None:
    provider = FakeRewrites(['s == "1e-30"'])

    ran = run_rewrites(COUNTED, {"s": "0", "n": 0}, provider)

    [line_4] = [record for record in ran.records if 4 in record.covered_lines]
    assert line_4.source is Source.REWRITE
    assert line_4.args == {"s": "1e-30", "n": 1}
    assert len(provider.requests) == 1
    # the pass's sat ask counts as the solver's sat, as its seconds do
    asked = [record for record in ran.records if record.solver_seconds is not None]
    assert line_4 in asked
    assert ran.result.solver.sat == len(asked)


# llm-rewrite-input-drops-a-rewrite-that-took-the-other-side
def test_a_kept_rewrite_whose_input_took_the_other_side_is_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a rewrite kept at line 2 that is wrong: its inputs never take line 2's true side
    condition = Condition(Site(file_of("counted"), 2, 7), True)
    code = rewrite_code('s == "1e-29"', ("s", "n"), "<rewrite kept>")
    kept = Kept()
    kept.keep(condition, code, ("s", "n"))  # pyrefly: ignore[bad-argument-type]
    made = rewrites_module.Rewrites.__init__

    def with_kept(self: rewrites_module.Rewrites, *args: object) -> None:
        made(self, *args)  # pyrefly: ignore[bad-argument-type]
        self.kept = kept

    monkeypatch.setattr(rewrites_module.Rewrites, "__init__", with_kept)
    provider = FakeRewrites([])

    ran = run_rewrites(COUNTED, {"s": "1e-30", "n": 0}, provider)

    at = f"llm: rewrite for {file_of('counted')}:2:7"
    [rewritten] = [record for record in ran.records if record.source is Source.REWRITE]
    number = ran.records.index(rewritten) + 1
    assert rewritten.args == {"s": "1e-29", "n": 1}
    assert f"{at} dropped at input {number}: took the other side" in llm_said(ran.said)
    assert kept.codes == {}
    # the next input aimed at a fork under line 2's true side asks the original condition
    assert all(record.source is not Source.REWRITE for record in ran.records[number:])
