"""Parse LLM responses into Python input dicts.

LLMs return test inputs in three common shapes:

1. Markdown code fence with ``python`` hint::

       ```python
       [{"x": 1}, {"x": 2}]
       ```

2. Plain markdown code fence::

       ```
       [{"x": 1}]
       ```

3. Raw literal without fencing.

The parser tries ``ast.literal_eval`` first (safe). For LLM-generated
expressions like ``[{"x": "a" * 5}]`` that ``literal_eval`` rejects
but which represent the intended test input, we fall back to a
restricted ``eval`` with no ``__builtins__``.
"""

from __future__ import annotations

import ast
import logging
from typing import Any

log = logging.getLogger("ct.plugins.llm.parser")


def parse_input_list(content: str | None) -> list[dict[str, Any]]:
    """Extract a list of input dicts from an LLM response.

    Returns an empty list on any failure — the caller treats that as
    "plugin has nothing to offer" and falls through to the engine's
    next step.
    """
    if content is None:
        return []
    code = _extract_code_block(content)
    parsed = _safe_eval(code)
    if not isinstance(parsed, list):
        return []
    return [entry for entry in parsed if isinstance(entry, dict)]


def parse_single_input(content: str | None) -> dict[str, Any] | None:
    """Extract a single input dict from an LLM response.

    LLMs sometimes return a list even when asked for one resolution;
    this function accepts the first dict in that case so the plugin
    stays useful. Returns None on any failure.
    """
    if content is None:
        return None
    code = _extract_code_block(content)
    parsed = _safe_eval(code)
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        for entry in parsed:
            if isinstance(entry, dict):
                return entry
    return None


def _extract_code_block(content: str) -> str:
    """Extract Python code from markdown fences or return the raw text."""
    if "```python" in content:
        return content.split("```python", 1)[1].split("```", 1)[0].strip()
    if "```" in content:
        return content.split("```", 1)[1].split("```", 1)[0].strip()
    return content.strip()


def _safe_eval(code: str) -> Any:
    """Try ``ast.literal_eval`` first, then fall back to a no-builtins eval.

    The fallback handles LLM quirks like ``"a" * 5`` that are simple
    expressions but not pure literals. Running ``eval`` with
    ``__builtins__ = {}`` blocks name resolution for imports, file
    access, and other dangerous operations.
    """
    try:
        return ast.literal_eval(code)
    except (ValueError, SyntaxError):
        pass

    try:
        return eval(code, {"__builtins__": {}}, {})  # noqa: S307
    except Exception as exc:
        log.debug("LLM response parse failed: %s", exc)
        return None
