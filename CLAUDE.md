# pyct

Concolic testing for Python, rebuilt on the `v2` branch. The old code stays on
`main` as a behavior reference. Never copy from it.

- This is a generic tool. Logic specific to one library or one issue is not allowed.
- `uv` manages the environment. Python 3.12 is the floor.
- en-US spelling everywhere.

## Commands

- test: `uv run pytest tests/ -v --cov` — healthy: every test passes, no fewer pass than on the base branch, and it prints `Required test coverage of … reached`: branch coverage of `pyct` and `tools`, subprocesses included, is at or above `fail_under` in pyproject.toml. Drop `--cov` for a quick run. Needs cvc5 on PATH, like every run (https://cvc5.github.io/, or `brew install cvc5`). The compare tool's `legacy` tests build a checkout of `main` once per session, or reuse the one `PYCT_LEGACY_CHECKOUT` names; `-m "not legacy"` skips them
- lint: `uv run ruff check src/ tests/ tools/ && uv run python -m tests.line_limits src/ tests/ tools/ && uv run pyrefly check && uv run lint-imports` — healthy: `Line limits: … 0 broken.`, then `Contracts: 2 kept, 0 broken.` Style, sizes, types, import layers, and the compare tool never importing pyct
- format: `uv run ruff format src/ tests/ tools/`
- run: `uv run pyct run MODULE::FUNCTION --args '{"arg": value}'`
- sweep: `uv run pyct sweep PACKAGE [--list]` — runs each entry as its own `pyct run` in a temporary directory, and prints one JSON line per entry and per module that did not import or could not be read, then a summary line. `--list` runs none and needs no cvc5
- compare, per merge: `uv run python -m tools.compare_coverage --legacy DIR --set v2 --set fixtures --budget 5 --accepted tools/compare_coverage/accepted-per-merge.jsonl` — healthy: exit 0, every row `same`, `left out` or `accepted`. The file's first line records the 5 s limits it was made with. A change that closes or opens a gap reruns this with `--accept` and commits the file; a new file under `targets/` needs an entry in `tools/compare_coverage/targets.json`. DIR is a checkout of `main` with its own environment, its library extras included and on this checkout's Python release: `git worktree add DIR main && uv sync --project DIR --frozen --extra realworld --extra library --python X.Y.Z`, where X.Y.Z is what `uv run python -V` prints here
- compare, full run on demand: `uv run python -m tools.compare_coverage --legacy DIR --accepted tools/compare_coverage/accepted-full.jsonl` — every set at the default 30 s budget, against a file of its own, since a file holds one set of limits and the checker refuses a file made with others. The sets beyond the per-merge two are legacy's `examples`, run in place in DIR, and the `realworld` and `library` entry points of installed libraries, which each side imports from its own environment at the version the entry pins; the `compare-coverage` dependency group installs them here. The `library` set's seeds are the ones legacy's discovery wrote, mostly `0`, so most of its rows stop at the first input and say little about parity until sweep supplies better seeds

## Layout

Eleven flat packages under `src/pyct/`, one per layer, listed top to bottom in
import order. A package imports only what is below it; `import-linter`
enforces this. `cli.py` sits above the stack, `config` and `utils` below it.

```
.
├── src/pyct/
│   ├── cli.py        entry point
│   ├── sweep/        a package's entries and their seeds, listed in a process of its own,
│   │                 and one `pyct run` process per entry. `pyct sweep`
│   ├── llm/          the only LLM code. Implements the five provider protocols
│   ├── run/          run(target, seed, *, limits, isolation, tell) -> RunResult.
│   │                 Composition root for one run. isolation.py runs each input in a throwaway process
│   ├── rewrite/      the LLM source rewrite, whole flow in one place
│   ├── intercept/    builtin interception, one import hook: the target's package loads with
│   │                 a fixed set of operations substituted by calls into core, kept in
│   │                 `.pyct_cache/` or `$PYCT_CACHE_DIR`, and runs with `len`, `ord` and `chr`
│   │                 bound to core's own
│   ├── solver/       solve(prefix, leaves, timeout) -> Answer. The cvc5 subprocess.
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
│   ├── unit/         mirrors src/pyct/, one directory per layer
│   ├── compare_coverage/  the compare tool's unit/ and acceptance/ tests, and a stub legacy engine
│   ├── line_limits.py  the size rules ruff has no rule for, run by lint. Tested beside it
│   └── test_timeout.py  the per-test timeout ends a test stuck on coverage's lock
├── tools/            development tools outside pyct's layers. They never import pyct
│   └── compare_coverage/  v2's coverage against legacy's, target by target. `python -m tools.compare_coverage`
└── targets/          the programs pyct is pointed at, by the acceptance tests and the benchmark
    ├── ints/         a follow story's fixtures, under the type it follows
    ├── strs/         the same for strings
    ├── floats/       the same for floats
    ├── nested/       values inside an argument: a dict's and a list's
    └── sweep/        packages and modules `pyct sweep` lists and runs
```

`core` is the runtime behavior of a concolic value. `intercept` makes the
target's package call core where Python would not, through a fixed set of
substitutions made as Python imports it and the builtin functions it binds
in each module's builtins. Neither is a rewrite: `rewrite` is the next
paper's LLM source rewrite.

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
- Functions about 20 lines. Five parameters at most, not counting `self` or `cls`. Files under 500 lines.
- Lint fails a function with more than five parameters, more than 20 statements, complexity over 10 or more than 30 body lines, and a file of 500 lines or more. Ruff counts every parameter but `self`, `cls`, `*args`, `**kwargs` and dummy names such as `_` and `_name`, in functions not marked `@override` or `@overload`, and counts a docstring as a statement. `tests/line_limits.py` counts body lines from the line after the signature through the last statement, blank lines and comments between included, less the docstring.
- Logging with lazy `%` formatting. DEBUG internals, INFO milestones, WARNING recoverable, ERROR failures.
- A name or comment says what the code handles. It never lists what the code misses; such a list is never complete. When a review finds a claim that outruns its check, narrow the claim, or widen the check when the missed case is one the code will realistically meet.
- A test compares an error message from Python itself to what plain Python says in the same run. CPython rewords its errors between versions, and the project supports every version from 3.12.
