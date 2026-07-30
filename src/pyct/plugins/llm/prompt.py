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
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyct.engine.plugin.context import EngineContext

log = logging.getLogger("ct.plugins.llm.prompt")


@dataclass(frozen=True)
class PromptContextOptions:
    """Which static-analysis blocks the seed prompt carries.

    Every flag defaults off, so the prompt stays source-only unless a
    caller opts in. The three blocks are independent because they carry
    different information: callee sources expose branch predicates the
    entry function hides, the CFG restates control flow already visible
    in that source, and boundary values are extracted literals that
    include return-value strings alongside genuine input thresholds.
    """

    include_callees: bool = False
    include_cfg: bool = False
    include_boundary_values: bool = False
    max_depth: int = 3


def build_seed_prompt(
    ctx: EngineContext,
    options: PromptContextOptions | None = None,
) -> str:
    """Build a prompt asking the LLM to seed initial test inputs.

    Source + signature always; the static-analysis blocks selected by
    *options* are appended after the target. With no options the prompt
    is source-only, which is what the engine shipped.

    Parameters whose defaults aren't Python literals (callables,
    class instances) are excluded from the emitted parameter list so
    the LLM cannot fill them with ``None`` — e.g.
    ``validators.url(..., validate_scheme: Callable = _validate_scheme)``
    becomes unreachable when ``validate_scheme=None`` leaks into the
    seed. The target's real defaults are used for excluded params.
    """
    source = _get_source(ctx.target_function)
    sig = str(ctx.target_signature)
    param_names = _literalizable_params(ctx.target_signature)
    example_dict = ", ".join(f'"{p}": value' for p in param_names[:3]) or '"param": value'
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
            *_analysis_sections(ctx, options),
            "## Request",
            "Generate 6-10 test inputs covering:",
            "- Each branch of every if/elif/else",
            "- Boundary values around comparison operators",
            "- Edge cases (empty strings, zero, negative, None)",
            "- One or two typical valid inputs",
            "",
            "## Output format",
            "Return ONLY a Python list of dicts inside a ```python``` fence.",
            f"Each dict MUST use these exact parameter names: {param_names}",
            "Values must be self-contained literals (str/int/float/bool/None/list/dict).",
            "Do NOT reference any name from the function source.",
            "",
            "```python",
            "[",
            f"    {{{example_dict}}},",
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


def _analysis_sections(
    ctx: EngineContext,
    options: PromptContextOptions | None,
) -> list[str]:
    """Return the static-analysis blocks *options* asks for.

    Each block is built independently and each failure is swallowed:
    a target whose module or source cannot be resolved still gets a
    source-only prompt rather than no prompt at all.
    """
    if options is None:
        return []
    sections: list[str] = []
    if options.include_cfg:
        sections.extend(_cfg_section(ctx))
    if options.include_callees:
        sections.extend(_call_graph_section(ctx, options))
    return sections


def _cfg_section(ctx: EngineContext) -> list[str]:
    """Format the target's control-flow graph, or nothing on failure."""
    from pyct.plugins.llm.analysis.cfg_extractor import CFGExtractor
    from pyct.plugins.llm.analysis.cfg_formatter import format_cfg_for_llm

    try:
        cfg = CFGExtractor().extract(inspect.getsource(ctx.target_function))
        text = format_cfg_for_llm(cfg.nodes, cfg.edges)
    except Exception:  # noqa: BLE001 - context is optional, never fatal
        log.debug("CFG extraction failed for %s", ctx.target_function, exc_info=True)
        return []
    return [text, ""] if text.strip() else []


def _call_graph_section(
    ctx: EngineContext,
    options: PromptContextOptions,
) -> list[str]:
    """Format callee sources and branch conditions, or nothing on failure."""
    from pyct.plugins.llm.analysis.call_graph import CallGraphConfig, analyze_call_graph
    from pyct.plugins.llm.analysis.call_graph_formatter import format_call_graph_for_llm

    module = inspect.getmodule(ctx.target_function)
    if module is None or not getattr(module, "__file__", None):
        return []
    try:
        analysis = analyze_call_graph(
            ctx.target_function,
            module,
            CallGraphConfig(
                project_root=_project_root(module),
                max_depth=options.max_depth,
            ),
        )
        text = format_call_graph_for_llm(analysis, options.include_boundary_values)
    except Exception:  # noqa: BLE001 - context is optional, never fatal
        log.debug("Call graph analysis failed for %s", ctx.target_function, exc_info=True)
        return []
    return [text, ""] if text.strip() else []


def _project_root(module: object) -> str:
    """Directory bounding call-graph resolution for *module*'s target.

    Callees outside this tree are recorded as unresolved rather than
    followed, so the root decides how much of a dependency the analysis
    will read. The module's own directory keeps same-package helpers in
    scope without walking into site-packages.
    """
    import os

    return os.path.dirname(os.path.abspath(module.__file__))  # type: ignore[attr-defined]


def _get_source(target: object) -> str:
    """Best-effort source extraction; fall back to repr on failure."""
    try:
        return inspect.getsource(target)
    except (OSError, TypeError):
        return f"<source unavailable for {getattr(target, '__name__', repr(target))}>"


_LITERAL_DEFAULT_TYPES: tuple[type, ...] = (
    int,
    float,
    str,
    bool,
    bytes,
    type(None),
    tuple,
    list,
    dict,
)


def _literalizable_params(signature: inspect.Signature) -> list[str]:
    """Return parameter names whose defaults the LLM can emit as literals.

    Required params (no default) are always included — the LLM must
    supply a value. Optional params are kept only when the default is
    one of the primitive/container types Python literals can express;
    a ``Callable`` default or a custom-class default would force the
    LLM to hallucinate (typically ``None``), which then breaks the
    target at call time.
    """
    kept: list[str] = []
    for param in signature.parameters.values():
        if param.name == "self":
            continue
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        if param.default is inspect.Parameter.empty:
            kept.append(param.name)
            continue
        if isinstance(param.default, _LITERAL_DEFAULT_TYPES):
            kept.append(param.name)
    return kept
