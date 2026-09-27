"""Acceptance tests for the read-a-long-string-answer story.

Each test spawns ``python -P -m pyct`` through the harness. The first two run the real
cvc5; the third puts a cvc5 on ``PATH`` that answers the first solve in a form pyct cannot
read and hands every later one to the real cvc5.
"""

import shutil
from pathlib import Path

from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct, summary_line

LONG_ANSWER_FILE = str(REPO_ROOT / "targets" / "strs" / "long_answer.py")
TAIL_IS_Z = "targets.strs.long_answer::tail_is_z"
PAST_A_MILLION = "targets.strs.long_answer::past_a_million"
EITHER_END = "targets.strs.long_answer::either_end"
EMPTY = '{"s": ""}'
# ``return "far"``, which only an s of 70,001 characters ending in z runs
FAR = 3
# ``if s[1_000_000:] != "":``, which only an s past 1,000,000 characters takes
PAST_A_MILLION_FORK = (8, 7)

# cvc5's long form of a string, a value line pyct cannot read as any string
UNREADABLE = (
    "((arg.s (witness ((@var.witness String)) (! (= (str.len @var.witness) 3)"
    " :witness (98 sort_to_term(String) 3 0)))))"
)


def solver_lines(stdout: str) -> list[dict[str, object]]:
    return [line for line in input_lines(stdout) if line["source"] == "solver"]


def text_of(line: dict[str, object]) -> str:
    args = line["args"]
    assert isinstance(args, dict), line
    value = args["s"]
    assert isinstance(value, str), line
    return value


def covered_of(line: dict[str, object]) -> list[int]:
    covered = line["covered"]
    assert isinstance(covered, dict), line
    return [int(number) for number in covered.get(LONG_ANSWER_FILE, [])]


def unreadable_then_real_cvc5(tmp_path: Path) -> None:
    """A cvc5 whose first answer is sat with a value pyct cannot read; later ones are real."""
    real = shutil.which("cvc5")
    assert real is not None
    script = tmp_path / "cvc5"
    script.write_text(
        "#!/bin/sh\n"
        # PATH is the tmp directory while the test runs, so the script says where its tools are
        "PATH=/bin:/usr/bin\n"
        f'if [ "$1" != "--version" ] && [ ! -e "{tmp_path}/answered" ]; then\n'
        f'    : > "{tmp_path}/answered"\n'
        "    cat > /dev/null\n"
        "    echo sat\n"
        f"    echo '{UNREADABLE}'\n"
        "    echo '(error \"no reason after sat\")'\n"
        "    exit 0\n"
        "fi\n"
        f'exec "{real}" "$@"\n'
    )
    script.chmod(0o755)


# read-a-long-string-answer-hands-back-a-long-string
def test_hands_back_a_long_string() -> None:
    result = run_pyct(TAIL_IS_Z, EMPTY)

    assert result.returncode == 0, result.stderr[-2000:]
    long = [line for line in solver_lines(result.stdout) if len(text_of(line)) == 70_001]
    assert long, result.stderr[-2000:]
    assert text_of(long[0]).endswith("z")
    assert FAR in covered_of(long[0])


# read-a-long-string-answer-caps-a-string-answer
def test_caps_a_string_answer() -> None:
    result = run_pyct(PAST_A_MILLION, EMPTY)

    assert result.returncode == 0, result.stderr[-2000:]
    line, col = PAST_A_MILLION_FORK
    assert f"missed {LONG_ANSWER_FILE}:{line}:{col} unsat" in result.stderr.splitlines()
    summary = summary_line(result.stdout)
    assert summary["misses"] == [
        {"file": LONG_ANSWER_FILE, "line": line, "col": col, "why": "unsat"}
    ], summary
    assert solver_lines(result.stdout) == []


# read-a-long-string-answer-never-ends-the-run
def test_never_ends_the_run(tmp_path: Path) -> None:
    unreadable_then_real_cvc5(tmp_path)

    result = run_pyct(EITHER_END, EMPTY, path=str(tmp_path))

    assert result.returncode == 0, result.stderr
    summary = summary_line(result.stdout)
    misses = summary["misses"]
    assert isinstance(misses, list) and len(misses) == 1, summary
    assert misses[0]["why"] == "unknown", summary
    trace = result.stderr.splitlines()
    missed = f"missed {LONG_ANSWER_FILE}:{misses[0]['line']}:{misses[0]['col']} unknown"
    assert missed in trace, result.stderr
    # the reason names the line cvc5 wrote, and comes before the miss it explains
    reasons = [at for at, text in enumerate(trace) if UNREADABLE in text]
    assert reasons and reasons[0] < trace.index(missed), result.stderr
    # the run went on to the next fork, which the real cvc5 answers
    heads = [at for at, text in enumerate(trace) if text.startswith("solver {")]
    assert heads and heads[-1] > trace.index(missed), result.stderr
    solver = summary["solver"]
    assert isinstance(solver, dict) and solver["unknown"] == 1 and solver["sat"] >= 1, summary
