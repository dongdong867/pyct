"""The fenced code blocks of a model's reply, read by one rule for every LLM tool."""

from __future__ import annotations

import re

# a fenced code block: three backticks, a language tag of letters, digits, _, + or - if any, and
# spaces or tabs if any, then a line break; the code; then the next three backticks
_FENCE = re.compile(r"```[\w+-]*[ \t]*\n(.*?)```", re.DOTALL)


def code_blocks(text: str) -> list[str]:
    """The code of each closed fenced block in ``text``, in order, as written."""
    return _FENCE.findall(text)
