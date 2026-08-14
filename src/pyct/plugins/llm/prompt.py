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
    """How much of the target's call graph the seed prompt carries.

    Defaults off, so the prompt stays source-only unless a caller opts
    in. Callee sources are the one block worth sending: the entry
    function's body hides the predicates its helpers branch on, and
    nothing else in the call graph carries a fact that source does not.
    Reachable callees are inlined as source rather than summarised —
    a predicate stripped of the code around it states a value without
    stating what to do with it.
    """

    include_callees: bool = False
    max_depth: int = 3


def build_seed_prompt(
    ctx: EngineContext,
    options: PromptContextOptions | None = None,
) -> str:
    """Build a prompt asking the LLM to seed initial test inputs.

    Source + signature always. With ``include_callees`` the source of
    every function the target reaches is inlined into the same code
    fence, so the block reads as a module. With no options the prompt is
    source-only, which is what the engine shipped.

    Parameters whose defaults aren't Python literals (callables,
    class instances) are excluded from the emitted parameter list so
    the LLM cannot fill them with ``None`` — e.g.
    ``validators.url(..., validate_scheme: Callable = _validate_scheme)``
    becomes unreachable when ``validate_scheme=None`` leaks into the
    seed. The target's real defaults are used for excluded params.
    """
    source = _get_source(ctx.target_function)
    callees = _callee_sources(ctx, options)
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
            _target_heading(ctx, callees),
            "```python",
            _code_block(source, callees),
            "```",
            "",
            f"## Signature\n`{sig}`",
            "",
            "## Request",
            "Generate 6-10 test inputs covering:",
            _branch_bullet(callees),
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
    can aim at the uncovered branches. Callee sources are not inlined
    here — this prompt fires mid-run, where the uncovered-line list is
    the signal doing the work.
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


def _target_heading(ctx: EngineContext, callees: list[str]) -> str:
    """Name what the code fence holds, so extra defs don't read as noise."""
    if not callees:
        return "## Target"
    name = getattr(ctx.target_function, "__name__", "target")
    return f"## Target: {name} (plus every function it reaches)"


def _code_block(source: str, callees: list[str]) -> str:
    """Target source, followed by each reachable callee's source."""
    if not callees:
        return source
    return "\n".join([source.rstrip(), *callees])


def _branch_bullet(callees: list[str]) -> str:
    """Point the coverage instruction at whatever the fence actually holds."""
    if not callees:
        return "- Each branch of every if/elif/else"
    return "- Both outcomes of every branch, in the target and in the functions it calls"


def _callee_sources(
    ctx: EngineContext,
    options: PromptContextOptions | None,
) -> list[str]:
    """Source of every function the target reaches, or nothing on failure.

    A target whose module or call graph cannot be resolved still gets a
    source-only prompt rather than no prompt at all.
    """
    from pyct.plugins.llm.analysis.call_graph import CallGraphConfig, analyze_call_graph

    if options is None or not options.include_callees:
        return []
    module = inspect.getmodule(ctx.target_function)
    if module is None or not getattr(module, "__file__", None):
        return []
    try:
        analysis = analyze_call_graph(
            ctx.target_function,
            module,
            CallGraphConfig(project_root=_project_root(module), max_depth=options.max_depth),
        )
    except Exception:  # noqa: BLE001 - context is optional, never fatal
        log.debug("Call graph analysis failed for %s", ctx.target_function, exc_info=True)
        return []
    return [
        f"\n# called by {caller}\n{func.source.rstrip()}" for caller, func in _reached(analysis)
    ]


def _reached(analysis: object) -> list[tuple[str, object]]:
    """Pair each reachable function with its caller, in call order.

    Breadth-first from the target so a callee appears after the function
    that calls it, and each is attributed to that caller rather than to
    the entry point it was reached from.
    """
    by_name = {f.name: f for f in analysis.reachable_functions.values()}  # type: ignore[attr-defined]
    ordered: list[tuple[str, object]] = []
    seen: set[str] = set()
    queue = [analysis.target]  # type: ignore[attr-defined]
    while queue:
        caller = queue.pop(0)
        for called in caller.callees:
            func = by_name.get(called.rpartition(".")[2])
            if func is None or func.name in seen:
                continue
            seen.add(func.name)
            ordered.append((caller.name, func))
            queue.append(func)
    return ordered


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
