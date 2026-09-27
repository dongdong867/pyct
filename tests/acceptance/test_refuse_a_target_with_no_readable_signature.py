"""Acceptance tests for the refuse-a-target-with-no-readable-signature bug.

Each test spawns ``python -P -m pyct`` through the harness. Python's reason is read from
plain Python in this run, since CPython rewords its errors between versions; a reason that
names an object's address is compared with the address left out, since each process has
its own.
"""

import inspect
import re
from pathlib import Path

import pytest

from targets.load import unreadable_signatures
from tests.acceptance.harness import run_pyct

MODULE = "targets.load.unreadable_signatures"


def reason_for(name: str) -> str:
    """What plain Python says when it cannot read the signature of ``name`` in the module."""
    with pytest.raises(Exception) as refused:
        inspect.signature(getattr(unreadable_signatures, name))
    return str(refused.value)


def without_addresses(text: str) -> str:
    return re.sub(r"0x[0-9a-f]+", "0x…", text)


# refuse-a-target-with-no-readable-signature-refuses-a-builtin
def test_refuses_a_builtin() -> None:
    result = run_pyct(f"{MODULE}::pick", "--args", '{"x": 1}')

    assert result.stderr.splitlines() == [
        f"cannot read the signature of {MODULE}::pick: {reason_for('pick')}"
    ]
    assert "Traceback" not in result.stderr
    assert result.stdout == ""
    assert result.returncode == 1


# refuse-a-target-with-no-readable-signature-refuses-a-wrapper-loop
def test_refuses_a_wrapper_loop() -> None:
    result = run_pyct(f"{MODULE}::looped", "--args", '{"x": 1}')

    reason = reason_for("looped")
    assert "wrapper loop" in reason
    assert [without_addresses(line) for line in result.stderr.splitlines()] == [
        without_addresses(f"cannot read the signature of {MODULE}::looped: {reason}")
    ]
    assert "Traceback" not in result.stderr
    assert result.stdout == ""
    assert result.returncode == 1


# refuse-a-target-with-no-readable-signature-refuses-before-the-seed-and-cvc5
def test_refuses_before_the_seed_and_cvc5(tmp_path: Path) -> None:
    # PATH is an empty directory, so no cvc5 is on it
    result = run_pyct(f"{MODULE}::pick", path=str(tmp_path))

    assert result.stderr.splitlines() == [
        f"cannot read the signature of {MODULE}::pick: {reason_for('pick')}"
    ]
    assert "args" not in result.stderr
    assert "cvc5" not in result.stderr
    assert result.stdout == ""
    assert result.returncode == 1


# a SystemExit while the signature is read is a refusal too, never a silent exit 0
def test_refuses_a_signature_read_that_exits() -> None:
    result = run_pyct(f"{MODULE}::exits_while_read", "--args", '{"x": 1}')

    assert result.stderr.splitlines() == [
        f"cannot read the signature of {MODULE}::exits_while_read: SystemExit: 0"
    ]
    assert result.stdout == ""
    assert result.returncode == 1
