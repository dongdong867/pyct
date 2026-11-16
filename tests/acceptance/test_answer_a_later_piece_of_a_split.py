"""Acceptance test for a later piece of a split, answered within the solver's limit: a run that
reads twenty lines reaches the line behind a search of them."""

import json

from tests.acceptance.harness import input_lines, missed_lines, run_pyct
from tests.acceptance.test_follow_the_length_of_a_split import LENGTHS, covers, line_of
from tests.acceptance.test_lists import args_of, solved


# later-split-piece-answered-run: each ask about line 19 answers within the limit, so the run's
# order no longer rests on which of them ran out of time
def test_answers_each_ask_about_the_last_of_twenty_lines() -> None:
    seed = json.dumps({"s": "\n".join(["a"] * 20)})

    result = run_pyct(f"{LENGTHS}::found_beside_a_loop", seed, "--budget", "35", timeout=60)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    found = line_of("if found:")
    reached = [args_of(each) for each in solved(lines) if covers(each, found + 1)]
    assert any("END" in str(args["s"]).splitlines() for args in reached), lines
    searched, looped = line_of('found = "END" in lines'), line_of('if line == "x":')
    at_lines = [f":{searched}:", f":{looped}:", f":{looped + 2}:"]
    timed_out = [
        missed
        for missed in missed_lines(result.stderr)
        if " timeout" in missed and any(at in missed for at in at_lines)
    ]
    assert timed_out == [], timed_out
