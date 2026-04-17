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
        log.warning("LLM response did not parse to a list (got %s)", type(parsed).__name__)
        log.debug("Extracted code block:\n%s", code[:500])
        return []
    results = [_sanitize_dict(e) for e in parsed if isinstance(e, dict)]
    results = [e for e in results if e]
    if not results and parsed:
        log.warning("LLM response parsed to list but contained no usable dicts: %s", parsed[:3])
    return results


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


_SCALAR_TYPES = (str, int, float, bool, type(None), bytes)


def _sanitize_dict(d: dict[str, Any]) -> dict[str, Any] | None:
    """Strip non-primitive values from a seed dict, recursing into containers.

    LLMs sometimes generate ``lambda: None`` or ``print`` for callback
    parameters, and the restricted eval creates real function objects
    from these. A callable nested inside a seed value (e.g. ``{"curve":
    {"convert": lambda: None}}``) fails to pickle across the
    isolated-mode spawn boundary just as much as a top-level one —
    recurse into dicts and lists and replace any non-primitive with
    None so the whole structure is pickle-safe.
    """
    cleaned = {k: _sanitize_value(v) for k, v in d.items()}
    return cleaned if cleaned else None


def _sanitize_value(v: Any) -> Any:
    """Return v if pickle-safe by shape; recurse into containers; drop otherwise."""
    if isinstance(v, _SCALAR_TYPES):
        return v
    if isinstance(v, dict):
        return {k: _sanitize_value(inner) for k, inner in v.items()}
    if isinstance(v, (list, tuple)):
        sanitized = [_sanitize_value(x) for x in v]
        return type(v)(sanitized) if isinstance(v, tuple) else sanitized
    log.debug("Dropping non-primitive seed value: %r (%s)", v, type(v).__name__)
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

    If the whole-list parse fails (common when one entry has broken
    quotes like ``{"x": "{"nested"}"}``), falls back to per-entry
    parsing to recover as many valid entries as possible.
    """
    try:
        return ast.literal_eval(code)
    except (ValueError, SyntaxError):
        pass

    try:
        return eval(code, {"__builtins__": {}}, {})  # noqa: S307
    except Exception:
        pass

    # Per-entry fallback: split on lines that look like dict boundaries
    # and try to parse each independently.
    recovered = _recover_entries(code)
    if recovered:
        log.info(
            "Recovered %d entries via per-entry parsing (whole-list parse failed)",
            len(recovered),
        )
        return recovered

    log.warning("LLM response parse failed entirely")
    log.debug("Unparseable code:\n%s", code[:500])
    return None


def _recover_entries(code: str) -> list[dict[str, Any]] | None:
    """Try to parse individual dict entries from a broken list expression.

    Extracts lines that look like ``{...}`` and parses each one.
    """
    import re

    entries: list[dict[str, Any]] = []
    for match in re.finditer(r"\{[^{}]*\}", code):
        fragment = match.group(0)
        try:
            val = ast.literal_eval(fragment)
        except (ValueError, SyntaxError):
            try:
                val = eval(fragment, {"__builtins__": {}}, {})  # noqa: S307
            except Exception:
                continue
        if isinstance(val, dict):
            entries.append(val)
    return entries or None
