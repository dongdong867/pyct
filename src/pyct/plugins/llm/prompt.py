"""Prompt builders for the LLM plugin.

Three scenarios with separate prompts:

* ``build_seed_prompt`` — initial seed generation. Given the target's
  source + signature, asks the LLM for a diverse list of input dicts.
* ``build_plateau_prompt`` — recovery when coverage has stopped
  improving. Includes tried inputs and current coverage state so the
  LLM can aim at the uncovered paths.
* ``build_unknown_prompt`` — solver has returned UNKNOWN/ERROR on a
  specific constraint. The LLM sees the failing constraint and is
  asked for a single input that satisfies it.

Prompts are structured as plain text with markdown section headers
(``## Target``, ``## Request``, etc.). We ask for outputs in a
markdown code fence so the parser can extract them cleanly.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyct.engine.plugin.context import EngineContext


def build_seed_prompt(ctx: EngineContext) -> str:
    """Build a prompt asking the LLM to seed initial test inputs.

    Scoped to source + signature only. We intentionally omit CFG
    extraction and type context analysis (upstream helpers not
    ported in the rewrite). GPT-class models do fine on branch
    enumeration given just the source.
    """
    source = _get_source(ctx.target_function)
    sig = str(ctx.target_signature)
    return "\n".join(
        [
            "# Task: Generate Test Inputs for Maximum Code Coverage",
            "",
            "Analyze the following Python function and generate a diverse list",
            "of test inputs that together cover all branches.",
            "",
            "## Target",
            "```python",
            source,
            "```",
            "",
            f"## Signature\n`{sig}`",
            "",
            "## Request",
            "Generate 6-10 test inputs covering:",
            "- Each branch of every if/elif/else",
            "- Boundary values around comparison operators",
            "- Edge cases (empty strings, zero, negative, None)",
            "- One or two typical valid inputs",
            "",
            "## Output format",
            "Return ONLY a Python list of dicts inside a ```python``` fence.",
            "Each dict must use the exact parameter names and self-contained",
            "literal values (str/int/float/bool/None/list/dict). Do NOT reference",
            "any name from the function source.",
            "",
            "```python",
            "[",
            '    {"param": value1},',
            '    {"param": value2},',
            "]",
            "```",
        ]
    )


def build_plateau_prompt(ctx: EngineContext) -> str:
    """Build a prompt asking the LLM to recover from a coverage plateau.

    Includes the tried inputs and the covered-line summary so the LLM
    can aim at the uncovered branches. We skip the CFG because we don't
    ship a CFG extractor in the rewrite.
    """
    source = _get_source(ctx.target_function)
    tried_summary = "\n".join(f"- {inp}" for inp in ctx.inputs_tried[-10:])
    covered = sorted(ctx.covered_lines)
    return "\n".join(
        [
            "# Task: Recover from coverage plateau",
            "",
            "Coverage has stopped improving. Help find inputs that exercise",
            "the uncovered branches.",
            "",
            "## Target",
            "```python",
            source,
            "```",
            "",
            "## Covered lines so far",
            f"{covered}",
            "",
            f"## Current coverage ({ctx.coverage_percent:.1f}%)",
            f"{len(ctx.covered_lines)} of {ctx.total_lines} lines.",
            "",
            "## Already tried (last 10)",
            tried_summary or "- (none)",
            "",
            "## Request",
            "Generate 5-8 NEW inputs that try to reach the missing lines.",
            "Avoid re-testing inputs similar to those already tried.",
            "",
            "## Output format",
            "Return ONLY a Python list of dicts inside a ```python``` fence.",
            "Use exact parameter names, literal values only.",
        ]
    )


def build_unknown_prompt(ctx: EngineContext, constraint: object) -> str:
    """Build a prompt asking the LLM for a single input satisfying a
    constraint the solver couldn't solve (UNKNOWN or ERROR status).

    The constraint is included verbatim (as its string repr). The LLM
    should return ONE input dict — the engine treats the response as a
    ``Resolution`` via ``parse_single_input``.
    """
    source = _get_source(ctx.target_function)
    return "\n".join(
        [
            "# Task: Satisfy a specific branch constraint",
            "",
            "The SMT solver could not satisfy this constraint. Suggest a",
            "single test input for the target function that would drive",
            "execution into the branch the constraint guards.",
            "",
            "## Target",
            "```python",
            source,
            "```",
            "",
            "## Unsolved constraint",
            f"`{constraint}`",
            "",
            "## Request",
            "Return ONE input dict that matches the target's parameters.",
            "",
            "## Output format",
            "Return ONLY a Python dict inside a ```python``` fence:",
            "",
            "```python",
            '{"param1": value1, "param2": value2}',
            "```",
        ]
    )


def _get_source(target: object) -> str:
    """Best-effort source extraction; fall back to repr on failure."""
    try:
        return inspect.getsource(target)
    except (OSError, TypeError):
        return f"<source unavailable for {getattr(target, '__name__', repr(target))}>"
