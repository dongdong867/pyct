"""Acceptance tests for let-the-solver-choose-a-small-dict-s-walk-key, its limits and errors.

An int-keyed lookup the solver cannot answer within its limit gives up at once, as a str-keyed
one does; an ask with chosen walk keys that would run past its second goes on without them; and
a walk the target grows raises as Python does. Each test runs pyct through the command line.
"""

import json

import pytest

from targets.dicts import walk_keys
from tests.acceptance.harness import first_line, forks_of, input_lines, run_pyct, summary_line
from tests.acceptance.test_let_the_solver_choose_a_small_dict_s_walk_key import (
    SETTLED,
    WF,
    F,
    W,
    covered,
    ints,
    reached,
)
from tests.acceptance.test_lists import solved
from tests.acceptance.test_pass_keywords_through_a_downgrade import covered_in

LOOKED_UP_READ = 111
LOOKED_UP_RETURN = 112


def looked_up_seed(keys: int) -> str:
    """`looked_up`'s seed: n = 1, and an N-key int dict whose values are 0."""
    return json.dumps({"n": 1, **json.loads(ints(keys, 0))})


def misses_of(stdout: str) -> set[tuple[object, object, object]]:
    misses = summary_line(stdout)["misses"]
    assert isinstance(misses, list)
    return {(m["line"], m["col"], m["why"]) for m in misses}


# let-the-solver-choose-a-small-dict-s-walk-key-gives-up-a-large-int-key-lookup-at-once
@pytest.mark.serial
def test_gives_up_a_large_int_key_lookup_at_once() -> None:
    target = f"{W}::looked_up"
    result = run_pyct(target, looked_up_seed(3000), "--budget", "60", "--solver-timeout", "10")

    assert result.returncode == 0, result.stderr
    assert f"missed {WF}:{LOOKED_UP_READ}:11 unknown" in result.stderr.splitlines()
    solver = summary_line(result.stdout)["solver"]
    assert isinstance(solver, dict) and solver["timeout"] == 0, solver


# let-the-solver-choose-a-small-dict-s-walk-key-still-asks-a-1000-key-int-lookup
@pytest.mark.serial
def test_still_asks_a_1000_key_int_lookup() -> None:
    target = f"{W}::looked_up"
    result = run_pyct(
        target, looked_up_seed(1000), "--budget", "60", "--solver-timeout", "10", timeout=90
    )

    assert result.returncode == 0, result.stderr
    aimed = [
        line
        for line in solved(input_lines(result.stdout))
        if isinstance(line["aim"], dict) and line["aim"]["line"] == LOOKED_UP_READ
    ]
    assert any(
        line["mismatch_at"] is None and LOOKED_UP_RETURN in covered_in(line, WF) for line in aimed
    ), result.stdout[-2000:]


def led_by_zeros(zeros: int) -> str:
    """A 200-key int seed whose first values are 0 and the rest 9: the first pass that reads a
    value above 5, and so the first line-11 lookup of 1, is pass ``zeros``.

    From the 200-key seed of 9s the only line-11 flip a run makes is the seed's own, at pass 0,
    with one chosen key: the step guard gives that ask up only below 0.06 s, where the asks
    with fixed keys, 0.04 s at the median, run out of time too."""
    return json.dumps({"d": {str(key): 0 if key <= zeros else 9 for key in range(1, 201)}})


# let-the-solver-choose-a-small-dict-s-walk-key-falls-back-when-chosen-keys-are-given-up
def test_falls_back_when_chosen_keys_are_given_up() -> None:
    # at 0.2 s the step guard lets the ask with fixed keys through, and gives up the ask that
    # chooses three keys in 200 int keys: the line-11 flip at pass 2
    result = run_pyct(
        f"{SETTLED}::int_only", led_by_zeros(2), "--budget", "10", "--solver-timeout", "0.2"
    )

    assert result.returncode == 0, result.stderr
    assert f"missed {F}:11:15 unknown" in result.stderr.splitlines()
    assert (11, 15, "timeout") not in misses_of(result.stdout)
    reached(input_lines(result.stdout))


# let-the-solver-choose-a-small-dict-s-walk-key-falls-back-past-one-second
@pytest.mark.serial
def test_falls_back_past_one_second() -> None:
    # six chosen keys in 200 int keys would run past the second the ask with chosen keys gets,
    # so the step guard skips it: the line-11 flip at pass 5
    result = run_pyct(f"{SETTLED}::int_only", led_by_zeros(5), "--budget", "30", timeout=60)

    assert result.returncode == 0, result.stderr
    assert f"missed {F}:11:15 unknown" in result.stderr.splitlines()
    assert (11, 15, "timeout") not in misses_of(result.stdout)
    lines = input_lines(result.stdout)
    assert 12 in covered(lines, F)
    reached(lines)


# let-the-solver-choose-a-small-dict-s-walk-key-raises-as-python-on-a-walk-that-grows
def test_raises_as_python_on_a_walk_that_grows() -> None:
    result = run_pyct(f"{W}::grown", '{"d": {"ab": 9}}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    failure = first_line(result.stdout)["failure"]
    assert isinstance(failure, dict), result.stdout
    with pytest.raises(RuntimeError) as plain:
        walk_keys.grown({"ab": 9})
    assert failure == {"kind": "target_raised", "detail": f"RuntimeError: {plain.value}"}
    falls = [
        line
        for line in solved(input_lines(result.stdout))
        if (118, [">", ["[]", "d", ["key", "d", 0]], 5], False)
        in [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(line)]
    ]
    assert any(120 in covered_in(line, WF) for line in falls), result.stdout[-2000:]


# review of PR #138: an ask that holds places or chooses among listed keys only says nothing
# exact, so a flip v2 answers stays answered, and an unsat that names a walk key is unknown
@pytest.mark.parametrize(
    ("function", "seed", "line"),
    [
        ("grown_past_the_cap", '{"d": {"1": 9}}', 127),
        ("second_dict", '{"d": {"a": 9}, "e": {"x": 9}}', 138),
        ("copied_out", '{"d": {"a": 9}}', 145),
        ("lowered", '{"d": {"x": 9}}', 152),
        ("in_names", '{"d": {"x": 1}, "names": ["a"]}', 159),
        ("keyed_set", '{"d": {"a": 1}}', 174),
        ("keys_view", '{"d": {"a": 1, "b": 2}}', 181),
        ("most", '{"d": {"1": 0}}', 188),
        ("hashed_after", '{"d": {"a": 0, "b": 0}}', 197),
        ("seen_first", '{"d": {"a": 9}}', 206),
        ("pickled_key", '{"d": {"a": 0}}', 217),
        ("hex_key", '{"d": {"a": 0}}', 228),
    ],
    ids=[
        "past-the-cap",
        "a-second-dict",
        "a-plain-dict-of-walk-keys",
        "a-lowered-key",
        "a-list-search",
        "a-set-of-dataclass-keys",
        "a-keys-view-compare",
        "max-of-the-keys",
        "a-hash-after-a-compare",
        "a-set-of-walk-keys",
        "a-pickled-key",
        "a-hex-int",
    ],
)
def test_keeps_what_v2_answers(function: str, seed: str, line: int) -> None:
    result = run_pyct(f"{W}::{function}", seed, "--budget", "5")

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    solver = summary_line(result.stdout)["solver"]
    # an unsat stays only where it holds without every step that names a walk key; past the
    # cap, flips of `len(d) > 250` are unsat on v2 too
    assert isinstance(solver, dict), solver
    assert function == "grown_past_the_cap" or solver["unsat"] == 0, solver
    reached(lines)
    if function not in ("second_dict", "lowered"):
        # v2 covers these; the other two need a key no fork names, on v2 too
        assert line in covered(lines, WF)
