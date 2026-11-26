"""Acceptance tests for the a-rewrite-reads-an-object-s-fields story's kept rewrites: a rewrite that
reads a field and took the wanted side stands in for its condition in later asks, building the
object again in its child each time, and a field read covers a line only the condition's second
visit reaches.

The targets sit in ``targets/rewrites/objects.py``, so a condition's line is its line in that file.
"""

from pathlib import Path

import pytest

from pyct.results.record import Source
from pyct.run import rewrites as rewrites_module
from tests.acceptance.llm_rewrites import (
    FakeRewrites,
    file_of,
    llm_said,
    one_thread,  # noqa: F401
    run_rewrites,
)
from tests.acceptance.object_fields import (
    OBJECTS,
    READS_CODE,
    TOOK,
    builds_by,
    covers,
    form,
    noisy_log,  # noqa: F401
)

# `pay_then(order, n)`: `if float(order.code) == 1e-30:` on line 35, `if n > 0:` on 36,
# `return 2` on 37
PAY_THEN = f"{OBJECTS}::pay_then"
# `pick(order)`: `if order.code.startswith(word) and float(order.code) == 1e-30:` on line 43,
# the float compare at col 43, `return word` on 44
PICK = f"{OBJECTS}::pick"


# llm-rewrite-object-fields-kept-reused
def test_a_kept_field_read_stands_in_for_its_condition_in_a_later_ask() -> None:
    provider = FakeRewrites([READS_CODE])
    seed = {"order": form("Order", code="0"), "n": 0}

    ran = run_rewrites(PAY_THEN, seed, provider)

    assert f"llm: rewrite for {file_of('objects')}:35:7: {TOOK}" in llm_said(ran.said)
    assert covers(ran, 37)
    assert len(provider.requests) == 1


# llm-rewrite-object-fields-kept-builds-the-object-again
def test_each_run_of_a_kept_field_read_builds_the_object_again(
    noisy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    children: list[object] = []
    run_model = rewrites_module.run_model

    def counted(*args: object) -> object:
        children.append(args)
        return run_model(*args)  # pyrefly: ignore[bad-argument-type]

    monkeypatch.setattr(rewrites_module, "run_model", counted)
    seed = {"order": form("Noisy", code="0"), "n": 0}

    ran = run_rewrites(PAY_THEN, seed, FakeRewrites([READS_CODE]))

    assert covers(ran, 37)
    # the try's run, and at least one later ask the kept rewrite stood in
    assert len(children) >= 2
    assert builds_by(noisy) == (len(ran.records), len(children))


# llm-rewrite-object-fields-kept-covers-a-line-only-the-second-visit-reaches
def test_a_field_read_covers_a_line_only_the_condition_s_second_visit_reaches() -> None:
    provider = FakeRewrites([READS_CODE])

    ran = run_rewrites(PICK, {"order": form("Order", code="2")}, provider)

    rewritten = [record for record in ran.records if record.source is Source.REWRITE]
    assert any(44 in record.covered_lines for record in rewritten)
    assert len(provider.requests) == 1
