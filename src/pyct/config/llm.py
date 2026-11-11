"""The LLM's settings as ``--llm`` and ``--llm-model`` write them, and the refusal of wrong ones."""

from __future__ import annotations

from dataclasses import dataclass

from pyct.config.command_line import UsageError

# every LLM tool this version has, in the order ``--llm all`` lists them
TOOLS = ("seeds",)
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


@dataclass(frozen=True)
class LlmSettings:
    """The tools a run switches on, in ``TOOLS`` order, and the model they ask."""

    tools: tuple[str, ...]
    model: Model = DEFAULT_MODEL


def parse_llm(tools_text: str | None, model_text: str | None) -> LlmSettings | None:
    """The settings ``--llm`` and ``--llm-model`` give, or None when ``--llm`` is not given.

    ``--llm`` is tool names joined by commas, or ``all``. ``--llm-model`` without ``--llm`` is
    refused, so a forgotten switch is not a plain run that looks like an LLM one.
    """
    if tools_text is None:
        if model_text is not None:
            raise UsageError("--llm-model needs --llm")
        return None
    tools = _tools(tools_text)
    model = DEFAULT_MODEL if model_text is None else _model(model_text)
    return LlmSettings(tools, model)


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
