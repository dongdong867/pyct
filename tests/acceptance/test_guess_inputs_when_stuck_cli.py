"""Acceptance tests for the guess-inputs-when-stuck story through ``pyct run``: ``--llm guesses``
and ``--llm all`` switch the tool on, ``--llm summaries,rewrites`` leaves it off, and a recorded
run replays its guess ask with no model called.

Each run's base URLs point at a stub on localhost or at a local port nothing listens on, and
neither real key reaches pyct, so no request leaves the machine.
"""

from pathlib import Path

from tests.acceptance.harness import input_lines, summary_line
from tests.acceptance.llm_guesses import file_of
from tests.acceptance.llm_stub import Stub, closed_port, llm_lines, llm_run, write_recording

HANDLER = "targets.guesses.handler::parse"
H = file_of("handler")
# the lines of the `except ValueError:` block no raise reached
ASKED = f"llm: guesses for {H}:8, {H}:9 (handler)"
SEED = '{"s": "0"}'


def guessed(stdout: str) -> list[dict[str, object]]:
    return [line for line in input_lines(stdout) if line["source"] == "guess"]


# llm-switch-per-tool-guesses
def test_llm_all_and_guesses_ask_for_guesses_and_summaries_rewrites_do_not(
    stub: Stub, tmp_path: Path
) -> None:
    stub.reply = "[]"

    for tools in ("all", "guesses"):
        asked = llm_run(stub.port, tmp_path, SEED, "--llm", tools, target=HANDLER)

        assert asked.returncode == 0, asked.stderr
        assert ASKED in llm_lines(asked.stderr)
    # the seeds ask and the guess ask of `all`, and the guess ask of `guesses`
    assert len(stub.received) == 3

    stub.received.clear()
    left_out = llm_run(stub.port, tmp_path, SEED, "--llm", "summaries,rewrites", target=HANDLER)

    assert left_out.returncode == 0, left_out.stderr
    assert not any(line.startswith("llm: guess") for line in llm_lines(left_out.stderr))
    assert stub.received == []

    refused = llm_run(stub.port, tmp_path, SEED, "--llm", "nope", target=HANDLER)

    assert refused.returncode == 2
    assert "it takes seeds, summaries, rewrites, guesses" in refused.stderr


def recorded_guess(folder: Path) -> Path:
    """A recording whose first guess ask answered `{"s": "x"}`, under a request text that differs
    from this run's."""
    reply = {
        "tool": "guesses",
        "place": f"{HANDLER}#1",
        "reply": '[{"s": "x"}]',
        "request": "lines this run does not ask about",
    }
    return write_recording(folder / "recorded.jsonl", [reply])


# llm-guess-for-a-stuck-line-replayed
def test_a_recorded_guesses_run_replays_its_first_guess_ask_with_no_model(
    stub: Stub, tmp_path: Path
) -> None:
    recorded = recorded_guess(tmp_path)

    replayed = llm_run(
        closed_port(),
        tmp_path,
        SEED,
        "--llm",
        "guesses",
        "--llm-replay",
        str(recorded),
        target=HANDLER,
    )

    assert replayed.returncode == 0, replayed.stderr
    lines = llm_lines(replayed.stderr)
    assert lines.index(ASKED) < lines.index(f"llm: guess 1 reached {H}:8, {H}:9")
    [found] = guessed(replayed.stdout)
    assert found["args"] == {"s": "x"}
    assert 'guess {"s": "x"}' in replayed.stderr.splitlines()
    llm = summary_line(replayed.stdout)["llm"]
    assert isinstance(llm, dict)
    assert (llm["asks"], llm["replayed"], llm["skipped"]) == (0, 1, 0)
    assert stub.received == []


# llm-guess-for-a-stuck-line-wait-not-counted, as the summary's `llm` entry counts it
def test_the_llm_entry_counts_the_wait_for_a_guess_reply(stub: Stub, tmp_path: Path) -> None:
    stub.reply = '[{"s": "x"}]'
    stub.delay = 2.0

    result = llm_run(stub.port, tmp_path, SEED, "--llm", "guesses", target=HANDLER)

    assert result.returncode == 0, result.stderr
    llm = summary_line(result.stdout)["llm"]
    assert isinstance(llm, dict)
    assert llm["asks"] == 1
    assert 2.0 <= llm["seconds"] < 30.0  # pyrefly: ignore[unsupported-operation]
