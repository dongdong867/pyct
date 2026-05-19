# Spec — native-contracts

**What.** Native `@pre("CONDITION")` / `@post("CONDITION")` decorators on user target functions, paired with a `discover_contracts(target) -> ContractSet` reader and the engine-side wiring (`_check_preconditions`, contracts lifecycle on `Engine`, threading through `EngineContext` / `ExplorationResult` / `ExplorationState`) that consumes them. Decorators attach a `ContractSet` to `target.__pyct_contracts__` at decoration time; engine reads via `discover_contracts`, filters violating concrete inputs via the existing skip path.

**Why.** Step 1 of a multi-step program toward concolic correctness/soundness checking (solve for input matching `@pre`, execute, verify `@post`). String predicates are SMT-translatable; lambda predicates are not — choosing strings now keeps the door open for solver-conjoin in a future step. The pre/post surface is the foundation for the postcondition oracle and solver-conjoin work tracked in `project_postpaper_brainstorm`.

**Trade-off accepted.** Build engine integration code (the contracts lifecycle on `Engine`, the `_check_preconditions` function, the contracts field across `EngineContext` / `ExplorationResult` / `ExplorationState`) directly on main rather than landing a third-party-backed scaffold first. The cost: this PR is larger than a pure-discovery-layer would be — engine code is in scope. Accepted because the alternative (land scaffold-branch's icontract integration to main, then replace it) ships and immediately retires a third-party dep that never had user approval. Reference the scaffold-branch design when transcribing engine wiring, but author against current main (which has telemetry / watchdog / post-loop work scaffold-branch predates).

## Feature DoD

When native-contracts ships:

- `discover_contracts(f)` returns a native-populated `ContractSet` for any function decorated with `@pre` / `@post`.
- `Engine.explore(target)` populates `Engine.contracts` from `discover_contracts(target)` before the first iteration and resets to `EMPTY_CONTRACTS` in the `explore()` finally; the contracts snapshot is observable via `EngineContext.contracts` from plugins and via `ExplorationResult.contracts` after the run.
- An engine exploration of an `@pre`-decorated function with a candidate input that violates the precondition observes the candidate filtered (via `_check_preconditions` returning a non-None violation string) rather than recorded as a successful exploration input.
- A module containing `@pre("invalid >>")` fails to import with `PyCTContractSyntaxError`.

## Behavior contract

Iron Law: happy + edge + error all covered. Each scenario below is what a consumer — the engine reading `discover_contracts(f)`, or a test author asserting on the returned `ContractSet` — observes.

### Scenario: happy path — single precondition discovered

```gherkin
Given a function f(x) decorated with @pre("x > 0")
When the consumer calls discover_contracts(f)
Then the returned ContractSet has exactly 1 require and 0 ensures
  And the require contract has condition_args == ("x",)
  And the require predicate returns True when called with x=5
  And the require predicate returns False when called with x=-1
```

### Scenario: happy path — postcondition with __return__ binding

```gherkin
Given a function f decorated with @post("__return__ > 0")
When the consumer calls discover_contracts(f)
Then the returned ContractSet has 0 requires and exactly 1 ensure
  And the ensure contract has condition_args == ()
  And the ensure contract has description == "__return__ > 0"
```

### Scenario: happy path — underscore shorthand for return value

```gherkin
Given a function f decorated with @post("_ > 0")
When the consumer calls discover_contracts(f)
Then the returned ContractSet has 0 requires and exactly 1 ensure
  And the ensure predicate's underlying code object lists "__return__" (not "_") in its co_names
  And the ensure predicate returns True when called with __return__=5
  And the ensure predicate returns False when called with __return__=-1
```

### Scenario: happy path — mixed pre and post

```gherkin
Given a function f(x) decorated with @pre("x > 0") and @post("__return__ == x * 2")
When the consumer calls discover_contracts(f)
Then the returned ContractSet has exactly 1 require and exactly 1 ensure
  And the require's condition_args == ("x",)
  And the ensure's condition_args includes "x"
```

### Scenario: happy path — stacked preconditions preserve source order

```gherkin
Given a function f(x, y) with @pre("x > 0") written above @pre("y < 10") in source
When the consumer calls discover_contracts(f)
Then the returned ContractSet has exactly 2 requires in source order
  And requires[0].description == "x > 0"
  And requires[1].description == "y < 10"
```

### Scenario: happy path — engine filters violating input via discovered contracts

```gherkin
Given a function f(x) decorated with @pre("x > 0")
  And the engine is exploring f with a candidate input where x == -1
When the engine evaluates preconditions for the candidate
Then the engine observes the candidate as filtered (precondition violation)
  And does not record it as a successful exploration input
```

### Scenario: edge case — predicate references name outside signature

```gherkin
Given a function f(x) decorated with @pre("z > 0") where z is not a parameter
When the consumer calls discover_contracts(f)
Then discovery succeeds and the require has condition_args == ()
  And when the engine evaluates the predicate it observes a NameError handled by the existing soft-fail path (WARN logged, exploration proceeds)
```

### Scenario: edge case — function with no contract decorators

```gherkin
Given a function f with no @pre or @post decorators
When the consumer calls discover_contracts(f)
Then the returned ContractSet is EMPTY_CONTRACTS
```

### Scenario: edge case — conjunction predicate over multiple parameters

```gherkin
Given a function f(x, y) decorated with @pre("x > 0 and y < 10")
When the consumer calls discover_contracts(f)
Then the require has condition_args == ("x", "y")
  And the predicate returns True only when both conjuncts hold
```

### Scenario: edge case — disjunction predicate over multiple parameters

```gherkin
Given a function f(x, y) decorated with @pre("x > 0 or y < 10")
When the consumer calls discover_contracts(f)
Then the require has condition_args == ("x", "y")
  And the predicate returns True when either conjunct holds
  And the predicate returns False only when both conjuncts fail
```

### Scenario: edge case — negation predicate

```gherkin
Given a function f(x) decorated with @pre("not (x == 0)")
When the consumer calls discover_contracts(f)
Then the require has condition_args == ("x",)
  And the predicate returns True for x != 0
  And the predicate returns False for x == 0
```

### Scenario: edge case — builtin reference excluded from condition_args

```gherkin
Given a function f(x) decorated with @pre("len(x) > 0")
When the consumer calls discover_contracts(f)
Then the require has condition_args == ("x",)
  And len is not present in condition_args
```

### Scenario: edge case — module-level constant resolved from target globals

```gherkin
Given a module defining MIN_VAL = 0 and a function f(x) decorated with @pre("x > MIN_VAL")
When the consumer calls discover_contracts(f) and the engine evaluates the predicate
Then the require has condition_args == ("x",) (MIN_VAL excluded)
  And the engine observes the predicate evaluating with MIN_VAL resolved from the target's __globals__
```

### Scenario: error path — invalid predicate syntax fails at decoration

```gherkin
Given a module source containing a function decorated with @pre("x >>")
When the consumer attempts to import the module
Then import fails with PyCTContractSyntaxError
  And PyCTContractSyntaxError is a subclass of SyntaxError
```

### Scenario: error path — predicate raises at engine eval time

```gherkin
Given a function f(x: int) decorated with @pre("x.foo()")
  And the engine is evaluating preconditions for a candidate where x is an int
When the engine evaluates the predicate
Then the engine observes the AttributeError via the existing soft-fail path (WARN logged, exploration proceeds)
```

### Scenario: error path — non-string decorator argument rejected at decoration

```gherkin
Given a function definition decorated with @pre(123)
When the decorator is applied at module import
Then a TypeError is raised at decoration time
  And the decorated function is not produced
```

## Schema and invariants

### Decorator surface

- Public surface: `@pre("CONDITION")` and `@post("CONDITION")` only — no PEP-316 docstring style, no `@invariant`.
- Decorators are attach-attr only: `@pre("x>0")` returns the original `f` with `f.__pyct_contracts__: ContractSet` set; `f is original_f` remains True; no wrapper, no runtime enforcement performed by the decorator itself.
- Storage is a single attribute `f.__pyct_contracts__: ContractSet`. Stacked decorators prepend to the existing tuple so that top-to-bottom source order corresponds to first-to-last position in the tuple.
- Non-string decorator argument (e.g., `@pre(123)`) raises `TypeError` at decoration time.
- Public module surface — `pyct.contracts` exports exactly: `pre`, `post`, `Contract`, `ContractSet`, `EMPTY_CONTRACTS`, `discover_contracts`, `PyCTContractSyntaxError`.

### Predicate compilation

- Predicate form is a string literal only — no lambdas, no callables. Enables future SMT translation.
- Compilation is eager: `compile(expr, '<contract>', 'eval')` runs at decoration time and the result is wrapped as a callable satisfying `predicate(**kwargs)`.
- The callable wrapper closes over the target function and evaluates the code object as `eval(code, target.__globals__, kwargs)`. This is the source-of-truth lookup chain for any name not in `condition_args` (builtins, module-level constants, imported names); without target's `__globals__` as the globals dict, the module-level-constant scenario would fail.
- Invalid predicate syntax raises `PyCTContractSyntaxError(SyntaxError)` at decoration time, failing module import loudly.
- `Contract.description` is the raw predicate string verbatim (pre-normalization for postconditions — `_` shown as written by author); no explicit `description=` kwarg is accepted.
- `Contract.description: str` is tightened (no longer `str | None`) — the native path always populates it.

### Discovery API

- `discover_contracts(target) -> ContractSet` reads `target.__pyct_contracts__` (via `getattr` with `EMPTY_CONTRACTS` default).
- A target with no `@pre` / `@post` decoration returns `EMPTY_CONTRACTS`.

### Engine integration

- `Engine` gains a `contracts: ContractSet` attribute initialized to `EMPTY_CONTRACTS` at construction.
- `Engine.explore(target)` populates `self.contracts = discover_contracts(target)` before the first iteration and before any plugin `on_exploration_start` dispatch; the populate runs before the AST `_try_rewrite` step so contract identity remains anchored to the original target.
- `Engine.explore(target)` resets `self.contracts = EMPTY_CONTRACTS` in the `finally` block so a subsequent explore on a different target starts clean.
- `EngineContext.contracts: ContractSet` is threaded through the `_snapshot` builder so plugins observe the read-only snapshot.
- `ExplorationResult.contracts: ContractSet` and `ExplorationState.contracts: ContractSet` fields surface the discovered set on the post-run result.
- `_check_preconditions(contracts: ContractSet, args: dict[str, Any]) -> str | None` evaluates each require predicate against the concrete `args` dict (bound to `condition_args`); returns `None` when all pass, `EMPTY_CONTRACTS.requires` is empty, or every predicate raised; returns `"precondition_violated: <source> <description>"` on the first failing predicate.
- Soft-fail paths inside `_check_preconditions`: a `KeyError` when binding `condition_args` from `args` logs a WARN naming the missing parameter and continues to the next contract; any exception raised by the predicate itself logs a WARN naming the contract source and continues (the engine never aborts on a contract-evaluation failure).
- This integration code is **transcribed in design from the scaffold-branch's `engine.py` / `plugin/context.py` / `state.py` / `result.py`**, but authored fresh against current main (which has post-loop discovery, plateau silencing, watchdog tombstones, and telemetry work that scaffold-branch predates).

### Postcondition return-value binding

- Canonical binding name is `__return__`; the shorthand `_` is accepted as equivalent (matches CrossHair convention).
- Normalization mechanism: at decoration time, the predicate string is parsed (`ast.parse(expr, mode="eval")`) and every `Name` node whose `id == "_"` is rewritten to `id = "__return__"` before `compile()` runs. The resulting code object's `co_names` always contains `__return__`, never `_`. Authors who wrote `_` and authors who wrote `__return__` produce identical predicate code objects.

### Name resolution

- `condition_args = tuple(name for name in code.co_names if name in signature.parameters)` — the intersection of the compiled predicate's referenced names and the target function's parameters.
- Names outside that intersection — builtins (`len`, `range`), module globals (`MIN_VAL`), return-value bindings (`__return__`, `_`) — are excluded from `condition_args` at discovery time.
- Names excluded from `condition_args` may still be resolved at engine eval time via Python's normal name lookup (builtins, the target's `__globals__`); unresolved names raise `NameError` and are handled by the engine's existing soft-fail path that WARNs and proceeds.
- `Contract.source` captures `file:line` via `inspect.stack()[1]` at decoration time, formatted as `"path:line"`; engine `_format_violation` reads it unchanged.

### Out of scope

These are intentionally excluded from this spec:

- PEP-316 docstring style (`pre: x > 0` in docstring).
- Runtime enforcement outside engine — no `enforce()`, no wrapper, no `PyCTViolationError`.
- Postcondition oracle (engine evaluating `@post` against return value) — deferred to a future spec.
- Solver-conjoin of preconditions for input synthesis — deferred to a future spec.
- Class invariants (`@invariant`).
- `icontract` dependency — not added; not adopted; not referenced. The scaffold-branch carrying icontract integration stays unmerged.
- `examples/` updates.
- Plugin protocol changes (plugin gains a read-only `contracts` field on its context snapshot; no new event types, no new dispatcher semantics).
