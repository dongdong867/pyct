"""The LLM's settings as ``--llm``, ``--llm-model`` and ``--llm-replay`` write them, and the
refusal of wrong ones."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pyct.config.command_line import UsageError

# the seeds tool's name, as ``--llm``, stderr and the code that builds it write it
SEEDS_TOOL = "seeds"
# every LLM tool this version has, in the order ``--llm all`` lists them
TOOLS = (SEEDS_TOOL,)
# the word ``--llm`` takes for every tool in TOOLS
ALL = "all"
# the providers ``--llm-model`` takes, each with an adapter of its own
PROVIDERS = ("anthropic", "openai")


@dataclass(frozen=True)
class Model:
    """A provider and one of its model ids. pyct keeps no list of ids: the provider says whether
    it knows the model."""

    provider: str
    name: str

    def __str__(self) -> str:
        return f"{self.provider}:{self.name}"


DEFAULT_MODEL = Model("openai", "gpt-6-luna")
# the tokens in and out together a run may spend on the LLM when ``--llm-limit`` is not given
DEFAULT_LIMIT = 100_000


@dataclass(frozen=True)
class LlmSettings:
    """The tools a run switches on, in ``TOOLS`` order, the model they ask, and the tokens the
    run may spend on them, in and out together.

    ``replay`` names a recording that answers each ask instead of the model, None to ask the
    model; a replay's model is the one the recording names.
    """

    tools: tuple[str, ...]
    model: Model = DEFAULT_MODEL
    replay: Path | None = None
    limit: int = DEFAULT_LIMIT


def parse_llm(
    tools_text: str | None,
    model_text: str | None,
    replay_text: str | None = None,
    limit_text: str | None = None,
) -> LlmSettings | None:
    """The settings ``--llm``, ``--llm-model``, ``--llm-replay`` and ``--llm-limit`` give, or
    None when ``--llm`` is not given.

    ``--llm`` is tool names joined by commas, or ``all``. Another LLM flag without ``--llm`` is
    refused, so a forgotten switch is not a plain run that looks like an LLM one. ``--llm-model``
    beside ``--llm-replay`` is refused too: a replay reports the model the recording names.
    """
    others = (("--llm-model", model_text), ("--llm-replay", replay_text))
    others += (("--llm-limit", limit_text),)
    if tools_text is None:
        given = [name for name, text in others if text is not None]
        if given:
            raise UsageError(f"{given[0]} needs --llm")
        return None
    if model_text is not None and replay_text is not None:
        raise UsageError("--llm-model and --llm-replay do not go together: a replay asks no model")
    tools = _tools(tools_text)
    model = DEFAULT_MODEL if model_text is None else _model(model_text)
    replay = None if replay_text is None else Path(replay_text)
    limit = DEFAULT_LIMIT if limit_text is None else _limit(limit_text)
    return LlmSettings(tools, model, replay, limit)


def _limit(text: str) -> int:
    """A whole number of tokens above zero, as ``int()`` reads one."""
    refusal = f"--llm-limit takes a positive number of tokens, got {text!r}"
    try:
        limit = int(text)
    except ValueError as error:
        raise UsageError(refusal) from error
    if limit <= 0:
        raise UsageError(refusal)
    return limit


def _tools(text: str) -> tuple[str, ...]:
    """The tools named, each once, in ``TOOLS`` order. A name pyct does not have is refused."""
    names = {part.strip() for part in text.split(",")}
    if ALL in names:
        names = (names - {ALL}) | set(TOOLS)
    unknown = sorted(names - set(TOOLS))
    if unknown:
        raise UsageError(
            f"--llm has no tool {unknown[0]!r}: it takes {', '.join(TOOLS)},"
            f" joined by commas, or {ALL} for every one"
        )
    return tuple(tool for tool in TOOLS if tool in names)


def _model(text: str) -> Model:
    """``PROVIDER:MODEL``, the provider one of ``PROVIDERS`` and the model not empty."""
    provider, _, name = text.partition(":")
    if provider not in PROVIDERS or not name:
        raise UsageError(
            f"--llm-model must be PROVIDER:MODEL, the provider {' or '.join(PROVIDERS)},"
            f" got {text!r}"
        )
    return Model(provider, name)
