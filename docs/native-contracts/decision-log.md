# Decision log — native-contracts

## spec-discussion

### Tier classification — standard
Single module replacement; engine wiring frozen (consumes existing `Contract`/`ContractSet`); narrow scenario set; no cross-cutting infra changes.

### Motivation lock
Step 1 toward correctness/soundness checking via concolic: solve for input matching `@pre`, execute, verify `@post`. This spec covers **read-only discovery** only; solver-conjoin + postcondition oracle deferred to future steps.

Replace icontract scaffold because:
- icontract integration brought no measurable benefit beyond a discovery shim
- Library is not actively maintained (drift-handling code already in `contracts.py:80-92` evidences past API surprise)
- Original brainstorm framing was "crosshair-like" (memory `project_postpaper_brainstorm`); icontract path was an unrecorded substitution
- String predicates align with PyCT's SMT future; lambda predicates do not

### Process gap acknowledged
Earlier icontract integration landed across 28 commits without recorded user approval. Current /df-plan invocation is the corrective discussion that should have run in May. Decision-log on disk + `docs/native-contracts/` artifacts close the gap going forward.

### Design locks

- **Decorator surface.** `@pre("CONDITION")` / `@post("CONDITION")` decorators only. No PEP-316 docstring style. No invariants.
- **Predicate form.** String literals (not lambdas). Enables future SMT translation.
- **Engine integration in scope.** `_check_preconditions`, `Engine.contracts` lifecycle, `EngineContext.contracts`, `ExplorationResult.contracts`, `ExplorationState.contracts` — all authored against current main. Reference scaffold-branch design (lifecycle order: populate before `_try_rewrite` AND before `on_exploration_start`; soft-fail patterns: KeyError on binding → WARN + skip-contract; predicate exception → WARN + skip-contract).
- **Postcondition return-value binding.** `__return__` canonical, `_` accepted shorthand. Matches CrossHair convention. **Normalization:** at decoration time, predicate string is parsed (`ast.parse(expr, mode="eval")`), every `Name` node with `id == "_"` rewritten to `id = "__return__"` before `compile()`. Resulting code object's `co_names` always contains `__return__`, never `_`. `Contract.description` keeps raw predicate string (pre-normalization).
- **Decorator behavior.** Attach-attr only — `@pre("x>0")` returns original `f` with `f.__pyct_contracts__` set. `f is original_f` stays True. No wrapper. No runtime enforcement.
- **Discovery API.** Reuse existing `Contract` / `ContractSet` shape. Replace `discover_contracts(target) -> ContractSet` body to read native metadata. Engine `_check_preconditions` calling convention (`Contract.predicate(**bound)`) unchanged.
- **Compile timing + globals binding.** Eager — `compile(expr, '<contract>', 'eval')` runs at decoration time; result wrapped as callable that closes over the target function and evaluates as `eval(code, target.__globals__, kwargs)`. Target's `__globals__` is the source-of-truth lookup chain for names not in `condition_args` (builtins, module-level constants, imported names) — required for module-level-constant scenario.
- **Storage layout.** Single attr `f.__pyct_contracts__: ContractSet`. Stacking semantics: each decorator prepends to existing tuple (top-to-bottom source = first in tuple).
- **Invalid syntax handling.** Fail-fast at decoration. Raise `PyCTContractSyntaxError(SyntaxError)`. Module import fails loudly.
- **Name resolution.** `condition_args = code.co_names ∩ signature.parameters`. Names outside intersection (builtins, module globals, `__return__`) ignored at discovery; engine eval-time NameError handled by existing soft-fail at `engine.py:498-506`.
- **Source field.** Capture file:line via `inspect.stack()[1]` at decoration time. Format `"path:line"`. Engine `_format_violation` reads unchanged.
- **Description field.** Derive from raw predicate string (`Contract.description = expr`). No explicit `description=` kwarg.
- **Description typing.** Tighten `Contract.description: str` (drop `| None`). Native path always populates.
- **Module surface.** Single `pyct.contracts` module exports: `pre`, `post`, `Contract`, `ContractSet`, `EMPTY_CONTRACTS`, `discover_contracts`, `PyCTContractSyntaxError`.

### Scenarios lock

**Happy:**
- single precondition discovered — `@pre("x > 0")` on `f(x)` → ContractSet with 1 require; `condition_args=("x",)`; predicate True on 5, False on -1
- postcondition with `__return__` binding — `@post("__return__ > 0")` → ContractSet with 1 ensure; `condition_args=()`; `description="__return__ > 0"`
- underscore shorthand for return value — `@post("_ > 0")` → equivalent code object; `co_names` contains `__return__` not `_`
- mixed pre and post — `@pre("x > 0") @post("__return__ == x * 2")` → 1 require + 1 ensure
- stacked preconditions preserve source order — `@pre("x > 0") @pre("y < 10")` on `f(x, y)` → 2 requires in source order
- engine filters violating input — `_check_preconditions` rejects candidate via discovered contract

**Edge:**
- predicate references name outside signature — `@pre("z > 0")` (z absent from params) → discover succeeds; `condition_args=()`; engine eval NameError → soft-fail WARN
- function with no contract decorators → `EMPTY_CONTRACTS`
- conjunction predicate over multiple parameters — `@pre("x > 0 and y < 10")` → `condition_args=("x","y")`; conjunction semantics
- builtin reference excluded from condition_args — `@pre("len(x) > 0")` → `len` builtin excluded; `condition_args=("x",)`
- module-level constant resolved from target globals — `@pre("x > MIN_VAL")` → `MIN_VAL` resolved from target's `__globals__` at eval

**Error:**
- invalid predicate syntax fails at decoration — `@pre("x >>")` → `PyCTContractSyntaxError`
- predicate raises at engine eval time — `@pre("x.foo()")` on int → AttributeError → soft-fail WARN + proceed
- non-string decorator argument rejected at decoration — `@pre(123)` → `TypeError`

### Out of scope (explicit-exclusion clauses)

- PEP-316 docstring style (`pre: x > 0` in docstring)
- Runtime enforcement outside engine — no `enforce()`, no wrapper, no PyCTViolationError
- Postcondition oracle (engine evaluates `@post` against return value)
- Solver-conjoin of preconditions for input synthesis
- Class invariants (`@invariant`)
- `icontract` dependency — not added, not adopted, not referenced; scaffold-branch stays unmerged
- `examples/` updates
- Plugin protocol changes (plugin gains read-only `contracts` field on context snapshot; no new event types, no new dispatcher semantics)

## plan-discussion

### ATDD-RED unit clarification
ATDD-RED unit = one commit per AC bullet in the plan task, NOT one commit per Gherkin scenario in `spec.md`. Gherkin scenarios are walking-spec / design-criteria reference that inform AC derivation but are not direct ATDD targets. Downstream `/df-implementation` consumes per-AC-bullet unit.

### Worktree-state pivot
Drafter dispatch surfaced that this worktree branched from `main`, where `src/pyct/contracts.py` does not exist, icontract is not in pyproject, and engine `_check_preconditions` is absent. The 28-commit scaffold lives only on unmerged `worktree-contracts-scaffold`, which is also stale relative to main (missing recent telemetry / watchdog / post-loop work). Original spec premise ("replace icontract scaffold") was wrong.

Pivot: **option 2 + reference-only**. Build native fresh on main; treat scaffold-branch as design rationale (not code lineage). Engine integration is in scope (the scaffold's engine wiring would otherwise be left half-done on main; building it native here is cleaner than landing scaffold first then replacing).

Spec rewritten to reflect: in-scope engine integration (lifecycle + `_check_preconditions` + context/result/state threading); no migration story; no test rewrite (no tests to migrate); no icontract dep ever added.

### Novelty assessment — standard
No novel architecture. Standard patterns throughout:
- Python decorators with closure
- `compile` + `eval` wrapper
- AST rewrite via `ast.NodeTransformer` (`_` → `__return__`)
- Module-level metadata attribute
- No new third-party deps (`ast`, `inspect`, `dataclasses` stdlib only)
- Engine lifecycle wiring is conventional dataclass-field threading + finally-block reset; design rationale transcribed from scaffold-branch's earlier validated approach

### Task enumeration — 3 tasks, linear order

Cohesion approach: each task owns one cohesive deliverable. Order chosen so every intermediate commit is functionally green (no half-broken states): engine sees `EMPTY_CONTRACTS` until decorators land; decorators populate the attribute that discovery + engine were already prepared to read.

- **Add `Contract`/`ContractSet` primitives + engine contract-lifecycle wiring** — touches `src/pyct/contracts.py` (new file: dataclasses + `EMPTY_CONTRACTS` + `discover_contracts` returning `getattr(target, '__pyct_contracts__', EMPTY_CONTRACTS)` + `_check_preconditions` with empty/violation/KeyError-soft-fail/predicate-exception-soft-fail branches) + `src/pyct/engine/engine.py` (lifecycle: populate before first iteration + before plugin dispatch; reset in `finally`) + `src/pyct/engine/plugin/context.py` (`EngineContext.contracts` field + `_snapshot` threading) + `src/pyct/engine/result.py` (`ExplorationResult.contracts` field) + `src/pyct/engine/state.py` (`ExplorationState.contracts` mirror). All wiring exercises through `EMPTY_CONTRACTS` end-to-end at this stage (no decorators exist yet). Engine lifecycle splits into 3 AC bullets (populate-before-iteration / populate-before-plugin-dispatch / reset-in-finally) per Iron Law "one AC bullet = one ATDD-RED commit".
- **Build `@pre`/`@post` decorators with predicate compilation** — touches `src/pyct/contracts.py` (adds `pre`, `post`, `PyCTContractSyntaxError`, `_compile_predicate`, `_normalize_underscore_to_return`, `_capture_source`). Populates `__pyct_contracts__` on decorated targets. Includes the discovery-identity AC for decorated targets (folded in from the previously-separate "Implement discover_contracts body" task — the stub from the foundation task already implements the body via `getattr` default; only the decorated-input test path is net-new here).
- **Verify engine wiring through native discovery (end-to-end)** — touches `tests/acceptance/` (new acceptance tests + fixtures under `tests/acceptance/fixtures/contracts/basic.py`). Covers engine-filters-violating-input, name-outside-signature soft-fail, module-constant resolved from `__globals__`, predicate AttributeError soft-fail.

### Greenfield outer-loop scaffold — not applicable
`src/pyct/contracts.py` does not exist on main, but the engine surface that consumes it does — Task 1 wires the engine pathway (the consumer) as part of the first task's deliverable. Pure bottom-up risk (building decorators before any consumer) is averted by Task 1 establishing the consumer-side wiring first against `EMPTY_CONTRACTS`.

### Order rationale
Engine pathway first with no-op (`EMPTY_CONTRACTS`) so the integration is testable in isolation. Decorators second so something populates `__pyct_contracts__` and the discovery identity becomes exercisable on decorated targets. End-to-end integration tests third, once decorators + discovery + engine pathway all present.

### Dependencies — linear
No parallel-eligible groups. No follower-task gates beyond the linear chain. Drop `## Dependencies` section from `plan.md`.

## review

### Reviewer findings triaged

`df-reviewer` single-pass alignment review surfaced 13 findings. Triage outcomes:

**Applied (with edits):**
- Reset AC bundle (#4) — split into post-explore-reset AC + cross-explore-independence AC.
- Engine iteration invokes `_check_preconditions` (#5) — added Task 1 AC + TDD entry; closes assumption gap that Task 3 was relying on unwired engine behavior.
- Pre-rewrite identity lock (#13) — added Task 1 AC + TDD entry asserting `discover_contracts` runs before `_try_rewrite`.
- Module-global resolution unit-level (#6) — added Task 2 AC + TDD entry exercising `eval(code, target.__globals__, kwargs)` at decorator unit boundary, not only end-to-end.
- `__all__` lockdown (#10) — added Task 2 AC + TDD entry asserting exact tuple matches the 7-export module-surface lock.
- Boolean composition split (#1, #2) — split the and/or/not bundled AC into 3 separate ACs (each its own ATDD-RED commit); added `or` and `not` scenarios to `spec.md ## Behavior contract` to close the orphan-assertion gap.
- DoD "not recorded" half (#9) — split Task 3 first AC into violation-string-surface AC + result-excludes-violating-candidate AC.
- `_check_preconditions` location (#7) — locked to `src/pyct/engine/engine.py` per spec engine-integration grouping; removed the "implementation choice during task" prose.
- Out-of-scope protocol affirmation (#11) — added TDD-plan note on `EngineContext.contracts` field-only extension confirming no new plugin protocol methods / event types / dispatcher branches.

**Accepted-without-fix (rationale):**
- Plugin context instance-identity AC (#3) — kept as-is. Plugins ARE the consumer of `EngineContext`; instance-identity vs decorated-target's `__pyct_contracts__` is the right test for context-snapshot threading. Reviewer's reframe to `on_iteration_start` handler observable adds indirection without strengthening the assertion.
- Source-capture shape check (#8) — kept as-is. Earlier in spec-discussion the `inspect.stack()[1]` + `path:lineno` shape was explicitly locked; the consumer of that field is the engine's `_format_violation`, but a unit-level shape check is the right ATDD-RED unit. End-to-end consumer surface is exercised by `_check_preconditions` violation string test in Task 1 which embeds source location in its output assertion.
- Suite-green AC (#12) — kept as-is. The developer running `uv run pytest tests/` IS the consumer; pytest-passing on the foundation task is a load-bearing observable per skill convention (verifies the engine + new wiring compose without regressing existing tests).

## retro

Minimal entry per user preference (full user-facing surface skipped). Patterns surfaced for internal tracking only; no memory mutations applied this run. Notable patterns observed: pre-baked positions before listening (cost ~5 turns + thrown-away draft); premise not grep-verified before authoring (drafter caught worktree-state mismatch); stale-branch design reference trap (scaffold predates main's telemetry work).
