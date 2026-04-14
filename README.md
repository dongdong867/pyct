# PyCT

Python concolic testing with LLM-assisted discovery oracles.

PyCT systematically explores program paths by alternating concrete execution
with SMT-constraint solving. When the SMT solver cannot decide a constraint or
coverage plateaus, an LLM is consulted as a recovery oracle to identify inputs
that cross code regions the solver cannot reach.

## Status

This is a ground-up rewrite of the original PyCT implementation, using a
plugin-based extension architecture and test-first development discipline.
The legacy version is preserved at `~/dev/pyct-legacy/` (commit `5620b2f`,
tag `pre-rewrite-archive`) for reference during the port.

## Requirements

- Python 3.12 or newer
- [uv](https://github.com/astral-sh/uv) for environment management
- [cvc5](https://cvc5.github.io/) installed as a system binary (`brew install cvc5`)

## Installation

```bash
uv sync                          # Core only
uv sync --extra llm              # With LLM plugin support
uv sync --extra benchmark        # With crosshair comparison baseline
uv sync --extra realworld        # With real-world benchmark fixtures
```

## Quick Start

```bash
uv run pyct run examples.basic.simple_branch::test_function
```

## Development

```bash
uv run pytest tests/ -v          # All tests
uv run pytest tests/acceptance/  # Acceptance tests only
uv run pytest tests/unit/        # Unit tests only
uv run ruff check src/ tests/    # Lint
uv run pyrefly check             # Type check
```

## Architecture

PyCT uses a single package (`src/pyct/`) with plugin-based extension:

- `core/` — Symbolic types (ported)
- `solver/` — Subprocess-based cvc5 wrapper (ported)
- `engine/` — Exploration engine + plugin protocol (new)
- `plugins/` — LLM and fuzzing plugins, in-tree

Extensions implement `pyct.engine.protocol.Plugin` and interact through
declared event hooks (collector, resolver, observer semantics).
