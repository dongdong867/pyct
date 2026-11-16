"""Acceptance tests for the a-rewrite-reads-no-object-a-hint-builds ticket: an object a class hint
builds is one a rewrite may not read, so the request does not show it as a dict, a rewrite that
reads it is refused, and the run goes on to its own stop instead of crashing.

The command-line cases replay a recording written here, so no model is called; the others run
``run()`` with a fake ``RewriteProvider`` that answers fixed text.
"""

import json
from pathlib import Path

import pytest

from pyct.run import run as run_module
from tests.acceptance.harness import run_pyct, stderr_lines, summary_line
from tests.acceptance.llm_rewrites import (
    FakeRewrites,
    file_of,
    llm_said,
    one_thread,  # noqa: F401
    run_rewrites,
)
from tests.acceptance.llm_stub import KEY_VARIABLES, closed_port, llm_env

MODULE = "targets.rewrites.hinted"
# `pay(order: Order)`: `if float(order.code) == 1e-30:` on line 2
PAY = f"{MODULE}::pay"
# `first(orders: list[Order])`: `if float(orders[0].code) == 1e-30:` on line 8
FIRST = f"{MODULE}::first"
# `charge(order: Order, s)`: `if float(s) == 1e-30:` on line 14
CHARGE = f"{MODULE}::charge"
READS_A_KEY = 'order["code"] == "1e-30"'
# a run that ends well within the test's time, its solver limit short enough that each
# condition runs out of it at once
REPLAY_LIMITS = ("--solver-timeout", "1", "--budget", "10")


def recording(path: Path, place: str, replies: list[str]) -> Path:
    """A recording of rewrites replies at ``place``, one for each try in order."""
    head = {"pyct_llm_recording": 1, "provider": "openai", "model": "gpt-6-luna"}
    lines = [json.dumps({**head, "tools": ["rewrites"]})]
    for attempt, reply in enumerate(replies, start=1):
        line = {"tool": "rewrites", "place": place, "try": attempt, "request": "", "reply": reply}
        lines.append(json.dumps({**line, "tokens": {"in": 1, "out": 1}, "seconds": 0.0}))
    path.write_text("".join(f"{line}\n" for line in lines))
    return path


def replayed(tmp_path: Path, spec: str, seed: str, replay: Path) -> tuple[int, str, str]:
    """``pyct run`` of ``spec`` from ``seed`` with rewrites answered from ``replay``."""
    result = run_pyct(
        spec,
        "--args",
        seed,
        "--llm",
        "rewrites",
        "--llm-replay",
        str(replay),
        *REPLAY_LIMITS,
        unset=KEY_VARIABLES,
        env=llm_env(tmp_path, closed_port()),
    )
    return result.returncode, result.stdout, result.stderr


# llm-rewrite-hint-built-object-is-not-read-as-a-dict
def test_a_hint_built_object_read_as_a_dict_is_refused_and_the_run_goes_on(tmp_path: Path) -> None:
    # the replies that ended the run with a traceback when the object read as a dict; since
    # a-rewrite-reads-an-object-s-fields a rewrite reads the object only as order.<field>, so
    # each is asked for and refused
    replay = recording(tmp_path / "hinted.jsonl", f"{MODULE}:2:7", [READS_A_KEY] * 4)

    code, stdout, stderr = replayed(tmp_path, PAY, '{"order": {"code": "0"}}', replay)

    assert code == 0, stderr
    assert "Traceback" not in stderr
    at = f"llm: rewrite for {file_of('hinted')}:2:7"
    said = [line for line in stderr_lines(stderr) if line.startswith(f"{at}, try ")]
    assert said == [
        f"{at}, try {number}: a rewrite may read order only as order.<field>"
        for number in range(1, 5)
    ]
    summary = summary_line(stdout)
    llm = summary["llm"]
    assert isinstance(llm, dict)
    assert llm["replayed"] == 4
    assert f"stopped: {summary['stopped']}" in stderr_lines(stderr)


# llm-rewrite-hint-built-object-in-a-list-is-not-read
def test_a_condition_on_a_list_of_hint_built_objects_is_given_up_unasked(tmp_path: Path) -> None:
    replay = recording(tmp_path / "hinted_list.jsonl", f"{MODULE}:8:7", [])

    code, stdout, stderr = replayed(tmp_path, FIRST, '{"orders": [{"code": "0"}]}', replay)

    assert code == 0, stderr
    at = f"llm: rewrite for {file_of('hinted')}:8:7"
    said = [line for line in stderr_lines(stderr) if line.startswith(at)]
    assert said == [f"{at} given up: no argument a rewrite may read"]
    llm = summary_line(stdout)["llm"]
    assert isinstance(llm, dict)
    assert (llm["asks"], llm["replayed"], llm["skipped"]) == (0, 0, 0)


# llm-rewrite-hint-built-object-refused-beside-a-plain-parameter
def test_a_rewrite_that_reads_a_hint_built_object_is_refused_and_the_next_one_runs() -> None:
    provider = FakeRewrites([READS_A_KEY, 's == "1e-30"'])

    ran = run_rewrites(CHARGE, {"order": {"code": "0"}, "s": "0"}, provider)

    at = f"llm: rewrite for {file_of('hinted')}:14:7"
    assert llm_said(ran.said)[:4] == [
        f"{at}: {READS_A_KEY}",
        f"{at}, try 1: a rewrite may read order only as order.<field>",
        f'{at}: s == "1e-30"',
        f"{at}: took the wanted side",
    ]
    request = provider.requests[0]
    assert dict(request.args)["order"] == "<holds an object>"
    assert request.unreadable == ()


# llm-rewrite-hint-built-object-leaves-a-run-without-rewrites-as-it-is
def test_a_run_without_rewrites_builds_no_rewrites_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(*_args: object) -> None:
        raise AssertionError("a run without rewrites built the rewrites tool")

    monkeypatch.setattr(run_module, "Rewrites", refused)

    ran = run_rewrites(PAY, {"order": {"code": "0"}}, None)

    assert llm_said(ran.said) == []
    assert ran.records
