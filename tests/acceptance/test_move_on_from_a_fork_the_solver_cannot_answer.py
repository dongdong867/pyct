"""Acceptance tests for the move-on-from-a-fork-the-solver-cannot-answer story.

Each test spawns ``python -P -m pyct`` through the harness and times the run by the
monotonic clock, because what the story promises is how long a run spends on a fork
cvc5 cannot answer. The ``order`` target has one: ``t <= s`` under ``s < t``, on two
tracked strings, which cvc5 1.3.4 does not answer even in 20 seconds.
"""

from tests.acceptance.harness import REPO_ROOT, run_pyct

ORDER = "targets.flip.order::order"
ORDER_FILE = str(REPO_ROOT / "targets" / "flip" / "order.py")
# takes ``s < t`` and not ``t <= s``
SEED = '{"s": "a", "t": "b"}'
# ``if s < t:``, which cvc5 flips alone in milliseconds
OUTER = 2
# ``if t <= s:``, which cvc5 cannot answer while ``s < t`` holds; ``t`` starts at column 11
INNER = 3
INNER_COL = 11
INNER_MISSED = f"missed {ORDER_FILE}:{INNER}:{INNER_COL} timeout"
# ``return "not below"``, which only an input that takes ``s < t`` false runs
NOT_BELOW = 6


# move-on-from-a-fork-the-solver-cannot-answer-refuses-a-bad-limit
def test_refuses_a_bad_limit() -> None:
    for bad in ["0", "-1", "nan", "inf", "abc"]:
        result = run_pyct(ORDER, SEED, "--solver-timeout", bad)

        assert result.returncode == 2, bad
        assert result.stdout == "", bad
        # the refusal alone, with no trace: the flags are read before the target is imported
        lines = result.stderr.splitlines()
        assert len(lines) == 1, result.stderr
        assert "solver timeout" in lines[0], result.stderr
        assert repr(bad) in lines[0], result.stderr
