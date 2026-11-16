"""Acceptance tests for the a-rewrite-reads-an-object-s-fields story: a rewrite reads a field of an
object argument, as ``order.code``, from the object the input builds; pyct solves it and runs its
input on the real code.

The targets sit in ``targets/rewrites/objects.py``, so a condition's line is its line in that file.
The command-line case replays a recording, so no model is called; the others run ``run()`` with a
fake ``RewriteProvider`` that answers fixed text.
"""

from pathlib import Path

import pytest

from pyct.run import run as run_module
from tests.acceptance.harness import input_lines, numbers_of, run_pyct, stderr_lines
from tests.acceptance.llm_rewrites import (
    FakeRewrites,
    file_of,
    llm_said,
    one_thread,  # noqa: F401
    run_rewrites,
)
from tests.acceptance.llm_stub import KEY_VARIABLES, closed_port, llm_env
from tests.acceptance.object_fields import (
    CHARGE,
    CHARGE_AT,
    HINTED_AT,
    OBJECTS,
    PAY,
    PAY_AT,
    PAY_HINTED,
    READS_CODE,
    TOOK,
    builds_by,
    covers,
    form,
    instance,
    noisy_log,  # noqa: F401
    order_seed,
)
from tests.acceptance.test_a_rewrite_reads_no_object_a_hint_builds import recording

# `tagged(order)`: `if float(order.tags[0]) == 1e-30:` on line 17
TAGGED = f"{OBJECTS}::tagged"


# llm-rewrite-object-fields-reads-a-seed-named-object
def test_a_field_of_an_object_the_seed_names_is_read_and_its_input_covers_the_line() -> None:
    ran = run_rewrites(PAY, order_seed(), FakeRewrites([READS_CODE]))

    said = llm_said(ran.said)
    assert said[said.index(f"{PAY_AT}: {READS_CODE}") + 1] == f"{PAY_AT}: {TOOK}"
    assert {"order": form("Order", code="1e-30")} in covers(ran, 6)


# llm-rewrite-object-fields-reads-a-bare-class-name
def test_a_field_of_an_object_named_by_its_bare_class_name_is_read() -> None:
    ran = run_rewrites(
        PAY, {"order": {"__class__": "Order", "code": "0"}}, FakeRewrites([READS_CODE])
    )

    assert f"{PAY_AT}: {TOOK}" in llm_said(ran.said)
    assert covers(ran, 6)


# llm-rewrite-object-fields-reads-an-object-a-hint-builds
def test_a_field_of_an_object_a_hint_builds_is_read() -> None:
    ran = run_rewrites(PAY_HINTED, {"order": {"code": "0"}}, FakeRewrites([READS_CODE]))

    assert f"{HINTED_AT}: {TOOK}" in llm_said(ran.said)
    assert {"order": {"code": "1e-30"}} in covers(ran, 12)


# llm-rewrite-object-fields-reads-an-instance-a-run-caller-hands-in
def test_a_field_of_an_instance_a_run_caller_hands_in_is_read() -> None:
    def seed() -> dict[str, object]:
        return {"order": instance(OBJECTS, "Order", "0")}

    ran = run_rewrites(PAY, seed, FakeRewrites([READS_CODE]))

    assert f"{PAY_AT}: {TOOK}" in llm_said(ran.said)
    assert covers(ran, 6)


# llm-rewrite-object-fields-reads-a-slot
def test_a_field_in_a_slot_is_read() -> None:
    ran = run_rewrites(PAY, order_seed("Slotted"), FakeRewrites([READS_CODE]))

    assert f"{PAY_AT}: {TOOK}" in llm_said(ran.said)
    assert covers(ran, 6)


# llm-rewrite-object-fields-reads-a-list-in-a-field
def test_an_item_of_a_list_in_a_field_is_read() -> None:
    seed = {"order": form("Tagged", tags=["0"])}

    ran = run_rewrites(TAGGED, seed, FakeRewrites(['order.tags[0] == "1e-30"']))

    assert f"llm: rewrite for {file_of('objects')}:17:7: {TOOK}" in llm_said(ran.said)
    assert {"order": form("Tagged", tags=["1e-30"])} in covers(ran, 18)


# llm-rewrite-object-fields-calls-a-method-of-the-field-s-value
def test_a_method_of_a_field_s_value_is_called() -> None:
    ran = run_rewrites(PAY, order_seed(), FakeRewrites(['order.code.strip() == "1e-30"']))

    assert f"{PAY_AT}: {TOOK}" in llm_said(ran.said)
    assert covers(ran, 6)


# llm-rewrite-object-fields-reads-what-the-constructor-stored
def test_a_field_is_read_as_the_constructor_stored_it() -> None:
    ran = run_rewrites(PAY, order_seed("Trimmed"), FakeRewrites(['order.code == "1E-30"']))

    assert f"{PAY_AT}: {TOOK}" in llm_said(ran.said)
    [args] = covers(ran, 6)
    order = args["order"]
    assert isinstance(order, dict)
    assert str(order["code"]).upper() == "1E-30"


# llm-rewrite-object-fields-runs-the-constructor-in-the-child
def test_the_constructor_runs_once_more_in_the_rewrite_s_child(noisy: Path) -> None:
    ran = run_rewrites(PAY, order_seed("Noisy"), FakeRewrites([READS_CODE]))

    assert f"{PAY_AT}: {TOOK}" in llm_said(ran.said)
    assert builds_by(noisy) == (len(ran.records), 1)


# llm-rewrite-object-fields-builds-no-object-for-a-plain-read
def test_a_rewrite_that_reads_no_object_builds_none(noisy: Path) -> None:
    seed = {"order": form("Noisy", code="0"), "s": "0"}

    ran = run_rewrites(CHARGE, seed, FakeRewrites(['s == "1e-30"']))

    assert f"{CHARGE_AT}: {TOOK}" in llm_said(ran.said)
    assert builds_by(noisy) == (len(ran.records), 0)


# llm-rewrite-object-fields-from-the-command-line
def test_a_recorded_field_read_is_replayed_from_the_command_line(tmp_path: Path) -> None:
    replay = recording(tmp_path / "fields.jsonl", f"{OBJECTS}:5:7", [READS_CODE])
    seed = '{"order": {"__class__": "targets.rewrites.objects::Order", "code": "0"}}'

    result = run_pyct(
        PAY,
        "--args",
        seed,
        "--llm",
        "rewrites",
        "--llm-replay",
        str(replay),
        "--solver-timeout",
        "1",
        "--budget",
        "10",
        unset=KEY_VARIABLES,
        env=llm_env(tmp_path, closed_port()),
    )

    assert result.returncode == 0, result.stderr
    assert f"{PAY_AT}: {TOOK}" in stderr_lines(result.stderr)
    rewritten = [line for line in input_lines(result.stdout) if line["source"] == "rewrite"]
    assert any(6 in numbers_of(line, "covered")[file_of("objects")] for line in rewritten)


# llm-rewrite-object-fields-leaves-a-run-without-rewrites-as-it-is
def test_a_run_without_rewrites_builds_no_rewrites_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(*_args: object) -> None:
        raise AssertionError("a run without rewrites built the rewrites tool")

    monkeypatch.setattr(run_module, "Rewrites", refused)

    ran = run_rewrites(PAY, order_seed(), None)

    assert llm_said(ran.said) == []
    assert ran.records
