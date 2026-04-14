- IMPORTANT: This is a generic python concolic testing tool — adding logic
  specific to a particular library or issue is NOT allowed
- Use `uv` as python environment management tool

## Project Architecture

PyCT is a generic Python concolic testing tool with a single-package layout
and plugin-based extension model:

- `src/pyct/core/` — Symbolic types (ConcolicInt, ConcolicStr, etc.) — ported from legacy
- `src/pyct/solver/` — SMT solver wrapper (subprocess to `cvc5` binary) — ported from legacy
- `src/pyct/engine/` — Exploration engine + plugin protocol + dispatcher — newly designed
- `src/pyct/plugins/llm/` — LLM discovery oracle plugin
- `src/pyct/plugins/fuzzing/` — Fuzzing strategy plugin
- `src/pyct/config/` — Configuration dataclasses
- `src/pyct/cli.py` — Command-line entry point

The previous codebase had a two-package split (`pyct` + `pyct_ext`) with an
unenforced boundary that extensions reached through. The rewrite unifies into
one package and uses the **plugin protocol** as the boundary — extensions
implement `pyct.engine.protocol.Plugin` and interact only through declared
event hooks.

## Plugin Protocol Rules

- Extensions go through `pyct.engine.protocol.Plugin`, NEVER subclass `Engine` directly
- Plugins access engine state only via the `EngineContext` passed to event hooks
- Three event semantics: **collector** (aggregate results from all plugins), **resolver** (race for first non-None response), **observer** (fire-and-forget)
- New plugins implement only the events they care about; defaults handle the rest

## Test-First Discipline

- New behavior requires a **failing test** before implementation. Red → Green → Refactor.
- Acceptance tests live in `tests/acceptance/` and use `examples/` as fixtures
- Unit tests live in `tests/unit/{core,solver,engine,plugins}/` mirroring `src/pyct/`
- Skip TDD only for trivial getters/setters and mechanical refactors
- **Ported modules** (`core/`, `solver/`) have characterization tests carried over from legacy — do not refactor them without first writing additional characterization tests to lock current behavior

## Python Conventions (PEP 8 + Modern Python 3.12+)

- **Naming**: `snake_case` for functions/variables/modules, `PascalCase` for classes,
  `UPPER_SNAKE_CASE` for constants. Custom exceptions end with `Error`.
- **Type hints**: Required on all public function signatures and dataclass fields.
  Use `X | None` syntax (PEP 604). Omit on trivial internal helpers.
- **Imports**: Explicit only. No wildcard `from x import *`.
  Group: stdlib → third-party → local, separated by blank lines.
- **String formatting**: `%`-formatting for logging (lazy evaluation). f-strings elsewhere.
- **Line length**: 100 chars soft limit.

## Project Thresholds

- Functions: max ~20 lines of logic. Extract sub-functions aggressively.
- Parameters: max ~5. Group into config/dataclass objects.
- Files: under 500 lines preferred.
- Classes: no god classes (>500 lines, >20 methods).

## Python-Specific Patterns

- Use `@dataclass(frozen=True)` for all configuration and value objects
- No static-only classes — use module-level functions
- Never `def f(items=[])` — use `None` + create inside
- Export only the public API from `__init__.py`

### Logging

- Levels: DEBUG=internals, INFO=flow/milestones, WARNING=recoverable, ERROR=failures
- Lazy formatting: `log.info("Found %d items", count)`

## Commands

- Run all tests: `uv run pytest tests/ -v`
- Run acceptance only: `uv run pytest tests/acceptance/ -v`
- Run unit only: `uv run pytest tests/unit/ -v`
- Run with coverage: `uv run pytest tests/ --cov=src --cov-report=term-missing`
- Type check: `uv run pyrefly check`
- Lint: `uv run ruff check src/ tests/`
- Format: `uv run ruff format src/ tests/`
- Run PyCT CLI: `uv run pyct run MODULE::FUNCTION --args '{"arg": value}'`

## Legacy Reference

The previous codebase is preserved at `~/dev/pyct-legacy/` (commit `5620b2f`,
tag `pre-rewrite-archive`, branch `feat/pyct-llm-integration`). Read it for
behavioral expectations when porting modules. **Do not import from it; copy
files into the new tree and adapt.**
