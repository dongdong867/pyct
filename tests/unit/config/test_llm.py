"""``--llm`` and ``--llm-model`` read into the run's LLM settings, and each one's refusal."""

import pytest

from pyct.config.command_line import UsageError
from pyct.config.llm import DEFAULT_MODEL, LlmSettings, Model, parse_llm


def test_no_llm_flag_is_no_llm() -> None:
    assert parse_llm(None, None) is None


def test_llm_seeds_takes_the_seeds_tool_with_the_default_model() -> None:
    assert parse_llm("seeds", None) == LlmSettings(tools=("seeds",), model=DEFAULT_MODEL)
    assert Model("openai", "gpt-6-luna") == DEFAULT_MODEL


def test_llm_all_takes_every_tool_pyct_has() -> None:
    assert parse_llm("all", None) == LlmSettings(tools=("seeds",), model=DEFAULT_MODEL)


def test_a_tool_named_twice_is_taken_once() -> None:
    assert parse_llm("seeds, seeds", None) == LlmSettings(tools=("seeds",), model=DEFAULT_MODEL)


@pytest.mark.parametrize("text", ["seeds,magic", "magic", "", "seeds,"])
def test_a_tool_pyct_does_not_have_is_refused_naming_it_and_the_tools(text: str) -> None:
    with pytest.raises(UsageError) as refused:
        parse_llm(text, None)

    wrong = [part.strip() for part in text.split(",") if part.strip() != "seeds"][0]
    assert repr(wrong) in str(refused.value)
    assert "seeds" in str(refused.value)
    assert "all" in str(refused.value)


def test_llm_model_picks_the_provider_and_the_model() -> None:
    settings = parse_llm("seeds", "anthropic:claude-sonnet-5-5")

    assert settings == LlmSettings(("seeds",), Model("anthropic", "claude-sonnet-5-5"))
    assert str(Model("anthropic", "claude-sonnet-5-5")) == "anthropic:claude-sonnet-5-5"


def test_a_model_name_keeps_every_colon_after_the_provider_s() -> None:
    settings = parse_llm("seeds", "openai:ft:gpt-6-luna:org")

    assert settings == LlmSettings(("seeds",), Model("openai", "ft:gpt-6-luna:org"))


@pytest.mark.parametrize("text", ["gemini:pro", "openai", "openai:", ":gpt", "OpenAI:gpt"])
def test_a_model_with_another_provider_or_no_model_is_refused_naming_the_providers(
    text: str,
) -> None:
    with pytest.raises(UsageError) as refused:
        parse_llm("seeds", text)

    message = str(refused.value)
    assert repr(text) in message
    assert "anthropic" in message
    assert "openai" in message


def test_llm_model_without_llm_is_refused() -> None:
    with pytest.raises(UsageError, match="--llm-model needs --llm"):
        parse_llm(None, "openai:gpt-6-luna")
