"""The summaries tests' autouse fixture imports each target module afresh and leaves
``sys.modules`` as it found it."""

import importlib
import sys
import types
from pathlib import Path

import pytest

from tests.acceptance import llm_summaries

FRESH = "targets.summaries.loops"
HELD = "targets.held_by_this_test"


def test_a_target_module_a_test_imported_is_gone_after_it_and_one_dropped_is_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delitem(sys.modules, FRESH, raising=False)
    held = types.ModuleType(HELD)
    monkeypatch.setitem(sys.modules, HELD, held)
    # the fixture's own generator, which pytest keeps as its definition's __wrapped__
    wrapped = llm_summaries.one_thread.__wrapped__  # pyrefly: ignore[missing-attribute]
    fixture = wrapped(monkeypatch, tmp_path)

    next(fixture)
    assert HELD not in sys.modules
    importlib.import_module(FRESH)
    with pytest.raises(StopIteration):
        next(fixture)

    assert FRESH not in sys.modules
    assert sys.modules[HELD] is held
