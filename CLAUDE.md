# pyct

Concolic testing for Python, rebuilt on the `v2` branch. The old code stays on
`main` as a behavior reference. Never copy from it.

- This is a generic tool. Logic specific to one library or one issue is not allowed.
- `uv` manages the environment. Python 3.12 is the floor.
- en-US spelling everywhere.

## Commands

- Tests: `uv run pytest tests/ -v`
- Lint: `uv run ruff check src/ tests/`
- Types: `uv run pyrefly check`
- Imports: `uv run lint-imports`
- Format: `uv run ruff format src/ tests/`
- Run: `uv run pyct run MODULE::FUNCTION --args '{"arg": value}'`

## Layout

Ten flat packages under `src/pyct/`, one per layer, listed top to bottom in
import order. A package imports only what is below it; `import-linter`
enforces this. `cli.py` sits above the stack, `config` and `utils` below it.

```
.
├── src/pyct/
│   ├── cli.py        entry point
│   ├── sweep/        one module: entries, seeds, triage. `pyct sweep`
│   ├── llm/          the only LLM code. Implements the five provider protocols
│   ├── run/          run(target, seed, *, budget, scope, helpers) -> RunResult.
│   │                 Composition root for one run. isolation.py runs `pyct run` in a subprocess
│   ├── rewrite/      the LLM source rewrite, whole flow in one place
│   ├── solver/       solve(prefix, leaves) -> Answer. The cvc5 subprocess.
│   │                 The only place the word solve appears
│   ├── branches/     the tree. The tree is the queue
│   ├── execution/    one call of the target. execute(ctx, args, deadline) -> ExecutionResult
│   ├── binding/      a dict becomes leaves and concolic values; a model becomes a dict again
│   ├── results/      InputRecord, RunResult, coverage, counters
│   ├── core/         what a concolic value does at runtime. Branch
│   ├── config/
│   └── utils/
├── tests/
│   ├── acceptance/   one test per acceptance criterion, through the CLI or run()
│   └── unit/         mirrors src/pyct/, one directory per layer
└── targets/          the programs pyct is pointed at, by the acceptance tests and the benchmark
```

`core` is the runtime behavior of a concolic value. `rewrite` is the source
rewrite that makes Python call core at all.

## Protocols

Five one-method protocols, each declared at its consumer and implemented in
`llm/`: `SummaryProvider` in core, `HintProvider` in solver, `RewriteProvider`
in rewrite, `SeedProvider` and `TriageProvider` in sweep. `Helpers()` with
nothing set is pure concolic. A helper never changes the tree and never reads
engine state.

## Conventions

- PEP 8. `snake_case` functions, `PascalCase` classes, `UPPER_SNAKE_CASE` constants. Exceptions end with `Error`.
- Type hints on every public signature and dataclass field. `X | None`.
- `@dataclass(frozen=True)` for config and value objects. No static-only classes. No mutable defaults.
- Explicit imports, grouped stdlib, third-party, local.
- Functions about 20 lines. Five parameters at most. Files under 500 lines.
- Logging with lazy `%` formatting. DEBUG internals, INFO milestones, WARNING recoverable, ERROR failures.
