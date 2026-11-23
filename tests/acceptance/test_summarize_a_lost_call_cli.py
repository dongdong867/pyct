"""Acceptance tests for the summarize-a-lost-call story through ``pyct run``: the token limit ends
the asks about loss sites, the summary line lists a loss site with its state, and a recorded run
replays its asks about loss sites.

Each run's base URLs point at a stub on localhost or at a local port nothing listens on, and
neither real key reaches pyct, so no request leaves the machine.
"""

from pathlib import Path

from tests.acceptance.harness import summary_line
from tests.acceptance.llm_stub import (
    Stub,
    closed_port,
    llm_lines,
    llm_run,
    read_recording,
    recordings,
)
from tests.acceptance.lost_calls import (
    DEEP,
    QUARTER,
    QUARTER_CODE,
    SHIFTED,
    C,
    place,
)

SEED = '{"n": 3}'


def asked_places(stub: Stub) -> list[str]:
    """The place each summaries ask the stub got names, read from its text."""
    texts = [str(each.body) for each in stub.received]
    return [text.split("Call `")[1].split(" at ")[1].split(",")[0] for text in texts]


# llm-summary-for-a-call-pyct-cannot-follow-stops-at-the-token-limit
def test_the_asks_about_loss_sites_end_at_the_token_limit(stub: Stub, tmp_path: Path) -> None:
    stub.reply = QUARTER

    result = llm_run(
        stub.port, tmp_path, SEED, "--llm", "summaries", "--llm-limit", "150", target=DEEP
    )

    assert result.returncode == 0, result.stderr
    assert asked_places(stub) == [place(36, 8)]
    assert "llm: token limit reached; no more asks" in llm_lines(result.stderr)
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# llm-summary-for-a-call-pyct-cannot-follow-checked-state
def test_the_summary_line_lists_a_loss_site_with_its_checked_formula(
    stub: Stub, tmp_path: Path
) -> None:
    stub.reply = QUARTER

    result = llm_run(stub.port, tmp_path, SEED, "--llm", "summaries", target=SHIFTED)

    assert result.returncode == 0, result.stderr
    llm = summary_line(result.stdout)["llm"]
    assert isinstance(llm, dict)
    assert llm["summaries"] == [
        {
            "kind": "call",
            "name": "__rshift__",
            "file": C,
            "line": 11,
            "col": 11,
            "changes": ["answer"],
            "formula": f"{QUARTER_CODE}\n",
            "condition": None,
            "state": "checked",
            "tries": 1,
            "checked_on": 1,
        }
    ]


def summary_said(stderr: str) -> list[str]:
    return [line for line in llm_lines(stderr) if line.startswith("llm: summary for")]


# llm-summary-for-a-call-pyct-cannot-follow-replayed
def test_a_recorded_ask_about_a_loss_site_is_answered_from_the_file(
    stub: Stub, tmp_path: Path
) -> None:
    stub.reply = QUARTER
    recorded = llm_run(stub.port, tmp_path, SEED, "--llm", "summaries", target=SHIFTED)
    assert recorded.returncode == 0, recorded.stderr
    [recording] = recordings(tmp_path)
    [_, reply] = read_recording(recording)
    assert (reply["tool"], reply["place"], reply["try"]) == ("summaries", place(11, 11), 1)
    replay = ("--llm", "summaries", "--llm-replay", str(recording))

    replayed = llm_run(closed_port(), tmp_path, SEED, *replay, target=SHIFTED)

    assert replayed.returncode == 0, replayed.stderr
    assert len(stub.received) == 1
    llm = summary_line(replayed.stdout)["llm"]
    assert isinstance(llm, dict)
    assert (llm["asks"], llm["replayed"], llm["skipped"]) == (0, 1, 0)
    said = summary_said(recorded.stderr)
    assert len(said) == 2
    assert summary_said(replayed.stderr) == said
