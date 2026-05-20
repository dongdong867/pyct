# Plan — native-contracts

3-task linear plan building native `@pre`/`@post` decorators + engine integration directly on main. No `icontract` dep adopted; the unmerged scaffold-branch serves as design reference for the engine lifecycle (populate-before-rewrite ordering, soft-fail patterns) but its code is not transcribed verbatim. Tasks ordered so every intermediate commit is functionally green: engine pathway lands first wired through `EMPTY_CONTRACTS`; decorators populate `__pyct_contracts__` next; discovery reads it; end-to-end acceptance tests verify last. Each AC bullet drives one ATDD-RED commit; behavior-observable framing throughout.

## Tasks

### Add `Contract`/`ContractSet` primitives + engine contract-lifecycle wiring

**AC:**
- a consumer running `from pyct.contracts import Contract, ContractSet, EMPTY_CONTRACTS, discover_contracts` observes successful imports; `EMPTY_CONTRACTS` is a `ContractSet` instance with `.requires == ()` and `.ensures == ()`
- a consumer calling `discover_contracts(any_undecorated_function)` observes `EMPTY_CONTRACTS` returned
- a consumer constructing `Engine(...)` observes `engine.contracts` equal to `EMPTY_CONTRACTS` before any `explore()` call
- a consumer calling `Engine.explore(target)` on any undecorated target observes `engine.contracts` populated via `discover_contracts(target)` before the first iteration runs
- a consumer with a spying plugin observes that the engine populates `engine.contracts` before any plugin `on_exploration_start` dispatch fires
- a consumer observes `engine.contracts` equal to `EMPTY_CONTRACTS` immediately after `Engine.explore(target)` returns
- a consumer running two consecutive `Engine.explore()` calls on different decorated targets observes each call seeing its own target's discovered contracts (no residue from the prior call)
- a consumer wrapping `target` so that `_try_rewrite` would transform it observes `engine.contracts` populated from discovery on the original (pre-rewrite) target identity — verified by attaching a marker `__pyct_contracts__` to the original target and observing the engine surfaces that marker, not an empty set from a rewritten copy
- a consumer running `Engine.explore(target)` on a `@pre`-decorated target whose concolic exploration produces a candidate input violating the precondition observes the engine invoking `_check_preconditions` on the candidate at iteration time and filtering it via the existing skip path (the candidate does not enter the successful-execution accounting)
- a plugin reading `ctx.contracts` from any event-hook dispatch observes the same `ContractSet` instance currently held by `Engine.contracts`
- a consumer reading `ExplorationResult.contracts` from the value returned by `Engine.explore(target)` observes the `ContractSet` discovered for that target
- a consumer calling `_check_preconditions(EMPTY_CONTRACTS, {"x": 1})` observes `None` returned (no contracts → no violation)
- a consumer calling `_check_preconditions(contracts_with_one_failing_require, {"x": -1})` observes a string starting with `"precondition_violated: "` and containing the contract's source location
- a consumer calling `_check_preconditions(contracts_whose_only_require_lists_a_param_absent_from_args, {"x": 1})` observes `None` returned, a WARN log captured by `caplog` naming the missing parameter, and no exception raised
- a consumer calling `_check_preconditions(contracts_whose_only_require_predicate_raises, {"x": 1})` observes `None` returned, a WARN log captured by `caplog` naming the contract source and the raised exception, and no exception propagated
- a consumer running `uv run pytest tests/` after the task lands observes a green suite (no regressions; engine continues to work because all undecorated targets see `EMPTY_CONTRACTS` and `_check_preconditions` is a no-op for them)

**TDD plan:** Per AC bullet, drive red→green:
- module exports: assert `from pyct.contracts import ...` succeeds → `src/pyct/contracts.py` (new file) — add `@dataclass(frozen=True)` for `Contract` and `ContractSet`, `EMPTY_CONTRACTS = ContractSet()`, stub `discover_contracts(target) -> ContractSet` returning `getattr(target, '__pyct_contracts__', EMPTY_CONTRACTS)`
- empty discovery: assert `discover_contracts(undecorated) is EMPTY_CONTRACTS` → same module — getattr-default path is the implementation
- engine init: assert `Engine(...).contracts is EMPTY_CONTRACTS` → `src/pyct/engine/engine.py` — add `self.contracts: ContractSet = EMPTY_CONTRACTS` to `__init__`
- engine lifecycle — populate before first iteration: assert `engine.contracts` equals `discover_contracts(target)` by the first iteration entry → `src/pyct/engine/engine.py` — wire `self.contracts = discover_contracts(target)` before the iteration loop (and before `_try_rewrite` so contract identity anchors to the original target)
- engine lifecycle — populate before plugin dispatch: assert spy plugin's first `on_exploration_start` observation sees `ctx.contracts` matching `discover_contracts(target)` → same module — populate must run before plugin dispatch in `_run`
- engine lifecycle — reset post-explore: assert `engine.contracts is EMPTY_CONTRACTS` immediately after `explore()` returns → `src/pyct/engine/engine.py` — wire `self.contracts = EMPTY_CONTRACTS` in `explore()` finally block
- engine lifecycle — cross-explore independence: assert two consecutive `explore()` calls on different decorated targets each see their own contracts → same module — covered by the finally reset; add test exercising both calls
- engine lifecycle — pre-rewrite identity: assert original-target discovery wins when `_try_rewrite` would otherwise replace the target → `src/pyct/engine/engine.py` — populate `self.contracts = discover_contracts(target)` BEFORE the `_try_rewrite` call so contract identity anchors to the original
- engine iteration invokes filter: assert spy/instrument captures that `Engine.explore()`'s iteration loop calls `_check_preconditions(self.contracts, candidate_args)` and skips candidates with non-None return → `src/pyct/engine/engine.py` — wire the precondition check into the iteration loop's candidate-evaluation path (existing skip-on-violation behavior preserved)
- plugin context threading: assert plugin's recorded `ctx.contracts` is the live `Engine.contracts` → `src/pyct/engine/plugin/context.py` — add `contracts: ContractSet` to `EngineContext`; thread via the existing `_snapshot` builder in engine. **Field-only extension:** no new plugin protocol methods, no new event types, no new dispatcher branches — honors `spec.md ## Schema and invariants > Out of scope` clause on plugin protocol.
- result field: assert `result.contracts` equals discovered set → `src/pyct/engine/result.py` — add `contracts: ContractSet` to `ExplorationResult`; `src/pyct/engine/state.py` — mirror on `ExplorationState`; engine passes through in `_build_result`
- `_check_preconditions` empty: assert returns `None` on `EMPTY_CONTRACTS` → `src/pyct/engine/engine.py` (locked here per spec engine-integration grouping) — add `_check_preconditions(contracts: ContractSet, args: dict[str, Any]) -> str | None`
- `_check_preconditions` violation: assert returns `"precondition_violated: <source>"` on failing require → same function — loop over `contracts.requires`, bind `condition_args` from `args`, eval predicate, return formatted violation string on first False
- `_check_preconditions` KeyError soft-fail: assert `caplog` captures WARN naming the missing param + function returns `None` (proceeds past the unbindable contract) → same function — wrap binding in `try/except KeyError`, log WARN, `continue` to next contract
- `_check_preconditions` predicate-exception soft-fail: assert `caplog` captures WARN naming the contract source + exception type + function returns `None` → same function — wrap predicate call in `try/except Exception`, log WARN, `continue` to next contract
- suite green: run `uv run pytest tests/` and observe green → all the above wiring must compose without regression

---

### Build `@pre`/`@post` decorators with predicate compilation

**AC:**
- a consumer running `from pyct.contracts import pre, post, PyCTContractSyntaxError` observes successful imports; `PyCTContractSyntaxError` is a subclass of `SyntaxError`
- a consumer applying `@pre("x > 0")` to a function `f(x)` then reading `f.__pyct_contracts__` observes a `ContractSet` with exactly 1 require where `condition_args == ("x",)`, `description == "x > 0"`, predicate returns True on `x=5` and False on `x=-1`, and `f is original_f` holds
- a consumer applying `@post("__return__ > 0")` to `f` observes `f.__pyct_contracts__.ensures[0]` with `condition_args == ()` and `description == "__return__ > 0"`
- a consumer applying `@post("_ > 0")` to `f` observes `f.__pyct_contracts__.ensures[0].predicate.__code__.co_names` contains `"__return__"` and does not contain `"_"`; predicate returns True when called with `__return__=5`, False with `__return__=-1`
- a consumer stacking `@pre("x > 0")` above `@pre("y < 10")` on `f(x, y)` observes `f.__pyct_contracts__.requires[0].description == "x > 0"` and `.requires[1].description == "y < 10"`
- a consumer mixing `@pre("x > 0")` and `@post("__return__ == x * 2")` on `f(x)` observes 1 require with `condition_args == ("x",)` and 1 ensure whose `condition_args` includes `"x"`
- a consumer applying `@pre("x > 0 and y < 10")` to `f(x, y)` observes `condition_args == ("x", "y")` and predicate True on `x=5, y=5`, False on `x=5, y=15`, False on `x=-1, y=5`
- a consumer applying `@pre("x > 0 or y < 10")` to `f(x, y)` observes `condition_args == ("x", "y")` and predicate True on `x=5, y=99` (left holds), True on `x=-1, y=5` (right holds), False on `x=-1, y=99` (neither)
- a consumer applying `@pre("not (x == 0)")` to `f(x)` observes `condition_args == ("x",)` and predicate True on `x=1`, False on `x=0`
- a consumer applying `@pre("len(x) > 0")` to `f(x)` observes `condition_args == ("x",)` (the builtin `len` is excluded from the intersection), predicate True on `x=[1]`, False on `x=[]`
- a consumer applying `@pre("x > MIN_VAL")` to `f(x)` defined in a module containing `MIN_VAL = 0` then reading `f.__pyct_contracts__.requires[0].predicate(x=5)` observes True returned (`MIN_VAL` resolved from target's `__globals__` at predicate eval, not as a `condition_args` binding); same consumer observes `condition_args == ("x",)` (the module-global `MIN_VAL` excluded from the intersection)
- a consumer applying `@pre("x > 0")` to `f(x)` then reading `f.__pyct_contracts__.requires[0].source` observes a string matching `"<test-file-path>:<lineno>"` where `lineno` is the source line carrying the `@pre("x > 0")` decorator
- a consumer calling `discover_contracts(f)` where `f` is decorated with `@pre("x > 0")` observes the returned `ContractSet` is the same instance as `f.__pyct_contracts__` (object identity)
- a consumer reading `pyct.contracts.__all__` observes exactly the tuple `("pre", "post", "Contract", "ContractSet", "EMPTY_CONTRACTS", "discover_contracts", "PyCTContractSyntaxError")`
- a consumer importing a module containing `@pre("x >>")` observes import failure raising `PyCTContractSyntaxError` (subclass of `SyntaxError`)
- a consumer applying `@pre(123)` observes `TypeError` raised at decoration time

**TDD plan:** Per AC bullet, drive red→green:
- decorator exports: assert `from pyct.contracts import pre, post, PyCTContractSyntaxError` succeeds → `src/pyct/contracts.py` — add `pre`, `post`, `PyCTContractSyntaxError(SyntaxError)`
- single precondition: assert `f.__pyct_contracts__.requires[0].condition_args == ("x",)` + predicate eval pair + `f is original_f` → `src/pyct/contracts.py:pre` — implement decorator + `_compile_predicate(expr, target) -> Contract`; `condition_args = tuple(name for name in code.co_names if name in inspect.signature(target).parameters)`; predicate wrapper closes over compiled code and target, evaluates as `eval(code, target.__globals__, kwargs)`
- single postcondition: assert ensure attrs match → `src/pyct/contracts.py:post` — mirror `pre`; invoke `_normalize_underscore_to_return` on the expression before compile so `_`→`__return__`
- underscore shorthand: assert `co_names` contains `__return__` not `_` + predicate eval pair on `__return__=` kwarg → `src/pyct/contracts.py:_normalize_underscore_to_return` — `ast.NodeTransformer` rewriting `Name(id="_", ctx=Load())` to `Name(id="__return__", ctx=Load())` before `compile()`
- stacked source order: assert `requires[0/1].description` ordering → covered by decorator's prepend semantic (each decorator constructs a new `ContractSet` with the new contract prepended); add test that exposes the order
- mixed pre+post: assert both populated → covered by composition of `pre` and `post`; add fixture combining both decorators
- boolean conjunction: assert `@pre("x > 0 and y < 10")` produces `condition_args == ("x", "y")` and truth table {(5,5)=True, (5,15)=False, (-1,5)=False} → `src/pyct/contracts.py:_compile_predicate` — `co_names ∩ signature.parameters` derivation must handle multi-name case in stable order; Python `eval()` handles `and` semantics for free
- boolean disjunction: assert `@pre("x > 0 or y < 10")` produces `condition_args == ("x", "y")` and truth table {(5,99)=True, (-1,5)=True, (-1,99)=False} → same function — `eval()` handles `or` for free; co_names derivation reused
- boolean negation: assert `@pre("not (x == 0)")` produces `condition_args == ("x",)` and truth table {1=True, 0=False} → same function — `eval()` handles `not` for free
- builtin exclusion: assert `condition_args == ("x",)` for `@pre("len(x) > 0")` → same function — the intersection filter is what makes this pass; without intersection, `len` would leak into `condition_args` and engine `_check_preconditions` would `KeyError` on binding
- module-global resolution (unit-level): assert `@pre("x > MIN_VAL")` on `f(x)` in a module defining `MIN_VAL = 0` yields `condition_args == ("x",)` and `predicate(x=5) is True` → `src/pyct/contracts.py:_compile_predicate` — wrapper must close over `target.__globals__` and pass it as the `globals` arg to `eval(code, target.__globals__, kwargs)`; without it, `MIN_VAL` raises `NameError`
- source capture: assert `requires[0].source` matches `"<test-file-path>:<lineno>"` → `src/pyct/contracts.py:_capture_source` (or inline in `pre`/`post`) — `inspect.stack()[1]` at decorator-call frame; format as `f"{frame.filename}:{frame.lineno}"`
- decorated discovery identity: assert `discover_contracts(decorated) is decorated.__pyct_contracts__` → no source change (foundation task's `getattr` default already implements this); test added here exercises the decorated path that only exists after this task
- `__all__` lockdown: assert `pyct.contracts.__all__ == ("pre", "post", "Contract", "ContractSet", "EMPTY_CONTRACTS", "discover_contracts", "PyCTContractSyntaxError")` → `src/pyct/contracts.py` — define `__all__` explicitly; enforces the decision-log module-surface lock
- invalid syntax: assert importing fixture module raises `PyCTContractSyntaxError` → `src/pyct/contracts.py:_compile_predicate` — catch `SyntaxError` from `compile()`, re-raise as `PyCTContractSyntaxError` preserving the original traceback context
- non-string arg: assert `pytest.raises(TypeError)` on `@pre(123)` → `src/pyct/contracts.py:pre` — defensive `isinstance(expr, str)` guard at function entry

---

### Verify engine wiring through native discovery (end-to-end)

**AC:**
- a consumer running `Engine.explore(f)` on `@pre("x > 0")`-decorated `f` with a concolic exploration producing a candidate input `x == -1` observes a `"precondition_violated: "`-prefixed violation string surfacing from the filter path on that iteration
- a consumer reading the `ExplorationResult` returned from the same `Engine.explore(f)` observes the violating candidate (`x == -1`) absent from the result's successful-execution accounting (no exploration record exists for the filtered input)
- a consumer running engine on `@pre("z > 0")` (where `z` is absent from the function's signature) observes a WARN log captured by `caplog` matching the soft-fail format from the foundation task, and exploration completes without crash
- a consumer running engine on `@pre("x > MIN_VAL")` (where `MIN_VAL` is a module-level constant in the target's module) observes the engine evaluating the predicate without raising `NameError` (verifies `eval(code, target.__globals__, kwargs)` actually uses target's globals end-to-end)
- a consumer running engine on `@pre("x.foo()")` for an int candidate `x` observes a WARN log captured by `caplog` matching the AttributeError soft-fail format from the foundation task, and exploration completes without crash

**TDD plan:** Per AC bullet, drive red→green:
- engine filter violation string: assert acceptance test in `tests/acceptance/test_native_precondition_skip.py` observes the `precondition_violated`-prefixed violation string on filtered iteration → engine code unchanged (already wired by foundation task); add `tests/acceptance/fixtures/contracts/basic.py` native-decorator fixture
- engine filter excludes from result: assert the same acceptance test reads `ExplorationResult` and confirms the violating candidate is not present in the successful-execution accounting → engine code unchanged; assertion against the existing result-shape surface
- name-outside-signature soft-fail: assert engine WARN captured via `caplog` + exploration completes → engine code unchanged; new test in `tests/acceptance/test_native_precondition_softfail.py`
- module-global resolution: assert engine evaluates without `NameError` → engine + decorator code unchanged; new acceptance test exercises full composition (decorator + discovery + engine eval against module globals)
- AttributeError soft-fail: assert engine WARN captured + exploration completes → engine code unchanged; new test in the same softfail file
