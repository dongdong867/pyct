"""What ``pyct run`` says and reads about the LLM: its flags, and the lines stderr gives."""

from __future__ import annotations

import argparse

from pyct.config.llm import ALL, DEFAULT_MODEL, PROVIDERS, TOOLS

# the Anthropic ids the help names as examples; pyct keeps no list of ids
ANTHROPIC_EXAMPLES = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")


def add_flags(parser: argparse.ArgumentParser) -> None:
    """``--llm TOOLS`` and ``--llm-model PROVIDER:MODEL``."""
    parser.add_argument(
        "--llm",
        dest="llm",
        metavar="TOOLS",
        help=(
            f"switch on LLM tools, joined by commas: {', '.join(TOOLS)}, or {ALL};"
            " the target's code goes to the provider"
        ),
    )
    parser.add_argument(
        "--llm-model",
        dest="llm_model",
        metavar="PROVIDER:MODEL",
        help=(
            f"the model the tools ask; the provider is {' or '.join(PROVIDERS)};"
            f" {DEFAULT_MODEL} by default, or for example anthropic:{ANTHROPIC_EXAMPLES[1]}"
            f" ({', '.join(ANTHROPIC_EXAMPLES)})"
        ),
    )
