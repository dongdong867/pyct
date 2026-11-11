"""``--llm`` and ``--llm-model`` read into the run's LLM settings, and each one's refusal."""

from pathlib import Path

import pytest

from pyct.config.command_line import UsageError
from pyct.config.llm import DEFAULT_MODEL, LlmSettings, Model, parse_llm


def test_no_llm_flag_is_no_llm() -> None:
    assert parse_llm(None, None) is None


def test_llm_seeds_takes_the_seeds_tool_with_the_default_model() -> None:
    assert parse_llm("seeds", None) == LlmSettings(tools=("seeds",), model=DEFAULT_MODEL)
    assert Model("openai", "gpt-6-luna") == DEFAULT_MODEL


def test_llm_all_takes_every_tool_pyct_has() -> None:
    expected = LlmSettings(tools=("seeds", "rewrites"), model=DEFAULT_MODEL)
    assert parse_llm("all", None) == expected


# llm-rewrite-switch-alone
def test_llm_rewrites_takes_the_rewrites_tool_alone() -> None:
    assert parse_llm("rewrites", None) == LlmSettings(tools=("rewrites",), model=DEFAULT_MODEL)


def test_the_tools_come_in_their_own_order_whatever_the_order_written() -> None:
    settings = parse_llm("rewrites,seeds", None)

    assert settings == LlmSettings(tools=("seeds", "rewrites"), model=DEFAULT_MODEL)


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


def test_llm_replay_names_the_recording() -> None:
    settings = parse_llm("seeds", None, replay_text="runs/one.jsonl")

    assert settings == LlmSettings(("seeds",), DEFAULT_MODEL, replay=Path("runs/one.jsonl"))


def test_the_limit_is_100_000_tokens_by_default() -> None:
    settings = parse_llm("seeds", None)

    assert settings is not None and settings.limit == 100_000


def test_llm_limit_takes_a_positive_number_of_tokens() -> None:
    settings = parse_llm("seeds", None, limit_text="1000")

    assert settings is not None and settings.limit == 1000


@pytest.mark.parametrize("text", ["0", "-1", "many", "1.5", ""])
def test_any_other_limit_is_refused(text: str) -> None:
    with pytest.raises(UsageError) as refused:
        parse_llm("seeds", None, limit_text=text)

    assert str(refused.value) == f"--llm-limit takes a positive number of tokens, got {text!r}"


@pytest.mark.parametrize(
    ("flag", "texts"),
    [("--llm-replay", {"replay_text": "r.jsonl"}), ("--llm-limit", {"limit_text": "10"})],
)
def test_another_llm_flag_without_llm_is_refused(flag: str, texts: dict[str, str]) -> None:
    with pytest.raises(UsageError) as refused:
        parse_llm(None, None, **texts)

    assert str(refused.value) == f"{flag} needs --llm"


def test_llm_model_beside_llm_replay_is_refused() -> None:
    with pytest.raises(UsageError) as refused:
        parse_llm("seeds", "openai:gpt-6-luna", replay_text="r.jsonl")

    assert "--llm-model" in str(refused.value)
    assert "--llm-replay" in str(refused.value)
