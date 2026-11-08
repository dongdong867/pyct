"""Acceptance tests for the run-from-several-seeds story.

Every test spawns ``python -P -m pyct`` through the harness with ``--seeds FILE``, a file of
JSON Lines the test writes. A refusal is a usage error: exit 2, nothing on stdout, and every
reason on stderr.
"""

import errno
import os
from pathlib import Path

from tests.acceptance.harness import input_lines, run_pyct, summary_line

# `bucket(x)`: x < 100, then x < 10 under it; 5, 50 and 500 take its three paths
BUCKET = "targets.flip.nested_checks::bucket"
# `echo(x)`: no fork at all
NO_CHECK = "targets.flip.no_check::echo"
# `three_deep(x)`: 30 and 31 take every check's true side, and no flip covers a new line
THREE_DEEP = "targets.flip.flips_gain_nothing::three_deep"
# `spin(x)`: never returns
NEVER_RETURNS = "targets.trace.never_returns::spin"
# `probe(x)`: raises below 10
RAISES = "targets.flip.raises_after_a_check::probe"
# `echo_text(s: str)`
TEXT = "targets.annotations.plain::echo_text"
# how the refusal of seeds given two ways starts
ONE_WAY = "give the seeds one way: after the target, through --args, or through --seeds"


def seeds_file(folder: Path, *lines: str, end: str = "\n") -> str:
    """A seeds file in ``folder`` holding ``lines``, each ended by a newline but the last,
    which ends with ``end``. Its path as the command line gives it."""
    path = folder / "seeds.jsonl"
    path.write_text("\n".join(lines) + end, encoding="utf-8")
    return str(path)


def seed_heads(stderr: str) -> list[str]:
    """The first line of each seed's trace."""
    return [line for line in stderr.splitlines() if line.startswith("seed ")]


def sources(stdout: str) -> list[object]:
    return [line["source"] for line in input_lines(stdout)]


def xs(stdout: str) -> list[object]:
    lines = input_lines(stdout)
    return [line["args"]["x"] for line in lines if isinstance(line["args"], dict)]


# run-from-several-seeds-in-file-order
def test_runs_each_seed_in_file_order_before_the_solver(tmp_path: Path) -> None:
    seeds = seeds_file(tmp_path, '{"x": 5}', '{"x": 500}')

    result = run_pyct(BUCKET, "--seeds", seeds)

    assert result.returncode == 0, result.stderr
    assert xs(result.stdout)[:2] == [5, 500]
    assert sources(result.stdout) == ["seed", "seed", "solver"]
    assert seed_heads(result.stderr) == [
        f'seed {seeds}:1 {{"x": 5}}',
        f'seed {seeds}:2 {{"x": 500}}',
    ]


# run-from-several-seeds-one-tree
def test_the_solver_works_from_every_seed_s_path(tmp_path: Path) -> None:
    seeds = seeds_file(tmp_path, '{"x": 5}', '{"x": 500}')

    result = run_pyct(BUCKET, "--seeds", seeds)

    assert result.returncode == 0, result.stderr
    solved = xs(result.stdout)[2:]
    assert len(solved) == 1, result.stdout
    assert isinstance(solved[0], int)
    assert 10 <= solved[0] < 100
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# run-from-several-seeds-blank-lines-ignored
def test_ignores_blank_lines_and_counts_every_line(tmp_path: Path) -> None:
    seeds = seeds_file(tmp_path, '{"x": 5}', "  ", '{"x": 500}')

    result = run_pyct(BUCKET, "--seeds", seeds)

    assert result.returncode == 0, result.stderr
    assert seed_heads(result.stderr) == [
        f'seed {seeds}:1 {{"x": 5}}',
        f'seed {seeds}:3 {{"x": 500}}',
    ]


# run-from-several-seeds-waiting-seed-is-work
def test_a_waiting_seed_keeps_the_run_going(tmp_path: Path) -> None:
    seeds = seeds_file(tmp_path, '{"x": 1}', '{"x": 2}')

    result = run_pyct(NO_CHECK, "--seeds", seeds, "--goal", "bugs")

    assert result.returncode == 0, result.stderr
    assert xs(result.stdout) == [1, 2]
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# run-from-several-seeds-plateau-after-the-seeds
def test_the_plateau_counts_after_the_last_seed(tmp_path: Path) -> None:
    seeds = seeds_file(tmp_path, '{"x": 30}', '{"x": 31}')

    result = run_pyct(THREE_DEEP, "--seeds", seeds, "--plateau", "1")

    assert result.returncode == 0, result.stderr
    assert sources(result.stdout) == ["seed", "seed", "solver"]
    assert summary_line(result.stdout)["stopped"] == "no gain in 1 inputs"


# run-from-several-seeds-budget-spent
def test_a_seed_that_spends_the_budget_stops_the_seeds(tmp_path: Path) -> None:
    seeds = seeds_file(tmp_path, '{"x": 1}', '{"x": 2}')

    result = run_pyct(NEVER_RETURNS, "--seeds", seeds, "--budget", "1")

    assert result.returncode == 0, result.stderr
    assert xs(result.stdout) == [1]
    assert summary_line(result.stdout)["stopped"] == "budget spent"


# run-from-several-seeds-full-coverage-skips-the-rest
def test_full_coverage_leaves_the_rest_of_the_seeds(tmp_path: Path) -> None:
    seeds = seeds_file(tmp_path, '{"x": 5}', '{"x": 50}', '{"x": 500}', '{"x": 7}')

    result = run_pyct(BUCKET, "--seeds", seeds)

    assert result.returncode == 0, result.stderr
    assert xs(result.stdout) == [5, 50, 500]
    assert summary_line(result.stdout)["stopped"] == "every line and branch covered"


# run-from-several-seeds-a-raise-goes-on
def test_a_seed_that_raises_does_not_stop_the_run(tmp_path: Path) -> None:
    seeds = seeds_file(tmp_path, '{"x": 1}', '{"x": 20}')

    result = run_pyct(RAISES, "--seeds", seeds)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert xs(result.stdout)[:2] == [1, 20]
    failure = lines[0]["failure"]
    assert isinstance(failure, dict)
    assert failure["kind"] == "target_raised"
    assert lines[1]["failure"] is None


# run-seeds-duplicate-skipped-same-seed
def test_skips_a_seed_an_earlier_line_gave(tmp_path: Path) -> None:
    seeds = seeds_file(tmp_path, '{"x": 5}', '{"x": 50}', '{"x":5}')

    result = run_pyct(BUCKET, "--seeds", seeds)

    assert result.returncode == 0, result.stderr
    assert xs(result.stdout)[:2] == [5, 50]
    assert sources(result.stdout).count("seed") == 2
    assert f"skipped {seeds}:3, same seed as line 1" in result.stderr.splitlines()


# run-seeds-file-refused-cannot-read
def test_refuses_a_file_it_cannot_read(tmp_path: Path) -> None:
    missing = str(tmp_path / "none.jsonl")

    result = run_pyct(BUCKET, "--seeds", missing)

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert result.stderr.splitlines() == [f"cannot read {missing}: {os.strerror(errno.ENOENT)}"]


# run-seeds-file-refused-no-seed
def test_refuses_a_file_with_no_seed(tmp_path: Path) -> None:
    seeds = seeds_file(tmp_path, "", "   ", "")

    result = run_pyct(BUCKET, "--seeds", seeds)

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert result.stderr.splitlines() == [f"{seeds} holds no seed"]


# run-seeds-file-refused-every-bad-line
def test_names_every_bad_line_at_once(tmp_path: Path) -> None:
    bad = ["not json", "[1]", '{"t": "a"}', '{"s": 5}']
    seeds = seeds_file(tmp_path, '{"s": "a"}', *bad)

    result = run_pyct(TEXT, "--seeds", seeds)

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    # each line's reason is what --args says of the same seed
    expected = []
    for number, text in enumerate(bad, start=2):
        alone = run_pyct(TEXT, "--args", text)
        assert alone.returncode == 2, alone.stderr
        expected += [f"{seeds}:{number}: {reason}" for reason in alone.stderr.splitlines()]
    assert result.stderr.splitlines() == expected


# run-seeds-file-refused-before-cvc5
def test_names_a_bad_line_before_it_looks_for_cvc5(tmp_path: Path) -> None:
    seeds = seeds_file(tmp_path, '{"s": 5}')

    result = run_pyct(TEXT, "--seeds", seeds, path=str(tmp_path))

    assert result.returncode == 2, result.stderr
    assert result.stderr.splitlines() == [f"{seeds}:1: s must be a str, got 5"]


# run-seeds-given-once-with-args
def test_refuses_seeds_beside_args(tmp_path: Path) -> None:
    seeds = seeds_file(tmp_path, '{"x": 5}')

    result = run_pyct(BUCKET, "--seeds", seeds, "--args", '{"x": 5}')

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert result.stderr.startswith(ONE_WAY), result.stderr


# run-seeds-given-once-with-positional
def test_refuses_seeds_beside_a_seed_after_the_target(tmp_path: Path) -> None:
    seeds = seeds_file(tmp_path, '{"x": 5}')

    result = run_pyct(BUCKET, '{"x": 5}', "--seeds", seeds)

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert result.stderr.startswith(ONE_WAY), result.stderr


# run-seeds-duplicate-skipped-same-seed, after a class target's notice
def test_says_a_skipped_seed_after_the_class_notice(tmp_path: Path) -> None:
    seeds = seeds_file(tmp_path, '{"owner": "ann"}', '{"owner": "bob"}', '{"owner":"ann"}')

    result = run_pyct("targets.classes.cart::Cart", "--seeds", seeds)

    assert result.returncode == 0, result.stderr
    notice = (
        "Cart is a class, so each input constructs it; name a method as Cart.<method> to run it"
    )
    assert result.stderr.splitlines()[:3] == [
        notice,
        f"skipped {seeds}:3, same seed as line 1",
        f'seed {seeds}:1 {{"owner": "ann"}}',
    ]
