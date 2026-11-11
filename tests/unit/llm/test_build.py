"""build finds a missing SDK or key before any ask, and otherwise gives the tools' helpers."""

import importlib.util
from pathlib import Path

import pytest

from pyct.config.llm import PROVIDERS, LlmSettings, Model
from pyct.llm.build import Built, Unusable, build
from pyct.llm.providers import PROVIDERS as TABLE
from pyct.llm.replay import ReplayCaller
from pyct.llm.rewrites import LlmRewrites
from pyct.llm.seeds import LlmSeeds
from pyct.results.llm_asks import Why
from pyct.run.helpers import Helpers
from tests.acceptance.llm_stub import DUMMY_KEY, write_recording

OPENAI = LlmSettings(("seeds",), Model("openai", "gpt-6-luna"))


def test_every_provider_the_flag_takes_has_a_row() -> None:
    assert sorted(TABLE) == sorted(PROVIDERS)


def test_a_provider_whose_package_is_not_installed_is_unusable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", DUMMY_KEY)
    found = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name, *rest: None if name == "openai" else found(name)
    )

    assert build(OPENAI) == Built(
        Helpers(), OPENAI.model, unusable=Unusable(Why.NO_PACKAGE, TABLE["openai"])
    )


@pytest.mark.parametrize("value", [None, ""])
def test_a_provider_whose_key_is_unset_or_empty_is_unusable(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is not None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", value)
    settings = LlmSettings(("seeds",), Model("anthropic", "claude-sonnet-5-5"))

    assert build(settings) == Built(
        Helpers(), settings.model, unusable=Unusable(Why.NO_KEY, TABLE["anthropic"])
    )


def test_a_usable_provider_gives_the_seeds_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", DUMMY_KEY)

    built = build(OPENAI)

    assert built.unusable is None
    assert isinstance(built.helpers.seeds, LlmSeeds)


# llm-rewrite-switch-alone
def test_the_rewrites_tool_alone_gives_its_helper_and_no_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", DUMMY_KEY)

    built = build(LlmSettings(("rewrites",), OPENAI.model))

    assert isinstance(built.helpers.rewrites, LlmRewrites)
    assert built.helpers.seeds is None


def test_no_tool_switched_on_gives_no_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", DUMMY_KEY)

    built = build(LlmSettings((), OPENAI.model))

    assert (built.helpers, built.model, built.unusable) == (Helpers(), OPENAI.model, None)


def test_a_usable_provider_records_to_a_new_file_in_the_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", DUMMY_KEY)

    built = build(OPENAI)

    assert built.connection is not None
    path = built.connection.recording.path
    assert path is not None and path.parent == tmp_path / "cache" / "llm" / "runs"


def test_a_replay_needs_no_key_and_reports_the_recorded_model(tmp_path: Path) -> None:
    recording = write_recording(tmp_path / "r.jsonl", [], model="anthropic:claude-opus-5-5")

    built = build(LlmSettings(("seeds",), replay=recording))

    assert built.unusable is None
    assert built.model == Model("anthropic", "claude-opus-5-5")
    assert built.connection is not None
    assert isinstance(built.connection.caller, ReplayCaller)
    assert isinstance(built.helpers.seeds, LlmSeeds)


def test_the_limit_is_the_ledger_s(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", DUMMY_KEY)

    built = build(LlmSettings(("seeds",), limit=1000))

    assert built.connection is not None and built.connection.ledger.limit == 1000
