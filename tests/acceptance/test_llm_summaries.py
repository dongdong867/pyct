"""The summaries tests' fixture imports each target module afresh and leaves ``sys.modules`` as
it found it."""

import importlib
import sys
import types

import pytest

from tests.acceptance.llm_summaries import targets_imported_afresh

FRESH = "targets.summaries.loops"
HELD = "targets.held_by_this_test"


def test_a_target_module_imported_in_the_block_is_gone_after_it_and_one_dropped_is_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, FRESH, raising=False)
    held = types.ModuleType(HELD)
    monkeypatch.setitem(sys.modules, HELD, held)

    with targets_imported_afresh():
        assert HELD not in sys.modules
        importlib.import_module(FRESH)

    assert FRESH not in sys.modules
    assert sys.modules[HELD] is held
