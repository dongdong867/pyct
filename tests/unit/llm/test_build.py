"""build finds a missing SDK or key before any ask, and otherwise gives the tools' helpers."""

import importlib.util

import pytest

from pyct.config.llm import PROVIDERS, LlmSettings, Model
from pyct.llm.build import Built, Unusable, build
from pyct.llm.providers import PROVIDERS as TABLE
from pyct.llm.seeds import LlmSeeds
from pyct.results.llm_asks import Why
from pyct.run.helpers import Helpers
from tests.acceptance.llm_stub import DUMMY_KEY

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

    assert build(OPENAI) == Built(Helpers(), Unusable(Why.NO_PACKAGE, TABLE["openai"]))


@pytest.mark.parametrize("value", [None, ""])
def test_a_provider_whose_key_is_unset_or_empty_is_unusable(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is not None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", value)
    settings = LlmSettings(("seeds",), Model("anthropic", "claude-sonnet-5-5"))

    assert build(settings) == Built(Helpers(), Unusable(Why.NO_KEY, TABLE["anthropic"]))


def test_a_usable_provider_gives_the_seeds_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", DUMMY_KEY)

    built = build(OPENAI)

    assert built.unusable is None
    assert isinstance(built.helpers.seeds, LlmSeeds)


def test_no_tool_switched_on_gives_no_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", DUMMY_KEY)

    assert build(LlmSettings((), OPENAI.model)) == Built(Helpers())
