"""The providers pyct asks through: each one's key variable, SDK package, extra and adapter."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    """A provider's name, the variable its SDK reads the key from, the SDK's package, the extra
    that installs it, and the module of pyct's adapter for it, which only the worker imports."""

    name: str
    key: str
    package: str
    extra: str
    adapter: str


PROVIDERS = {
    "anthropic": Provider(
        "anthropic", "ANTHROPIC_API_KEY", "anthropic", "pyct[anthropic]", "pyct.llm.anthropic_call"
    ),
    "openai": Provider(
        "openai", "OPENAI_API_KEY", "openai", "pyct[openai]", "pyct.llm.openai_call"
    ),
}
