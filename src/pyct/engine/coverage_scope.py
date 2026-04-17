"""Coverage scope — value object specifying what the engine measures.

A CoverageScope names the source files whose line coverage the engine
tracks, the executable lines within each file, and which lines count as
synthetically pre-covered (e.g., ``def`` headers that never fire a line
event during body execution).

Scopes are constructed by the caller, not the engine. Two factory
methods cover common cases:

- ``CoverageScope.for_target(target)`` — classical concolic scope. Tracks
  only the target function's own source file, restricted to executable
  lines within the function body. Pre-covers the ``def`` line.
- ``CoverageScope.for_paths(paths)`` — explicit multi-file scope. Tracks
  all lines deemed executable across a list of files. Used by benchmarks
  that measure library-wide coverage (e.g. ``yaml/*.py``).

Separating construction from tracking lets callers compute a scope once
and pass it through ``ExecutionConfig`` across the isolated-runner spawn
boundary. Scopes are immutable by contract (frozen dataclass) and
pickle-safe by construction (only strings, frozensets, and dicts of
primitive types).

Scopes are not hashable — their mapping fields are plain dicts for
simplicity. No code path hashes a scope; treat it as a read-only value.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from pyct.engine.function_inspector import _executable_statements, inspect_target


@dataclass(frozen=True, eq=True)
class CoverageScope:
    """Immutable specification of files, executable lines, and pre-covered lines.

    Attributes:
        files: Absolute source file paths the engine tracks.
        executable_lines: Per-file set of executable line numbers. Any
            line outside this set is ignored when coverage data arrives.
        pre_covered: Per-file lines that count as covered without firing
            a tracer event. Typically the ``def`` header line.
        target_file: The "primary" file for narrow-view reporting —
            plugin snapshots and ``ExplorationResult.executed_lines``.
            When a scope covers multiple files, the narrow view still
            reports only this file's coverage so LLM prompts continue
            to reason about the target function alone.
    """

    files: frozenset[str]
    executable_lines: Mapping[str, frozenset[int]]
    pre_covered: Mapping[str, frozenset[int]]
    target_file: str

    # Frozen dataclass would auto-generate __hash__ from field values, but
    # dict fields raise TypeError when hashed. Scopes are never put in a
    # set, so suppress hashing and keep __eq__ (dataclass default).
    __hash__ = None  # type: ignore[assignment]

    @classmethod
    def for_target(cls, target: Callable) -> CoverageScope:
        """Build a classical single-file scope for the given callable.

        Tracks the function's own source file only, with executable lines
        restricted to the function body. The ``def`` line is pre-covered
        so it doesn't stall ``is_fully_covered()`` — the tracer never
        fires on the def line during body execution.
        """
        target_file, func_lines, def_line = inspect_target(target)
        return cls(
            files=frozenset({target_file}),
            executable_lines={target_file: func_lines},
            pre_covered={target_file: frozenset({def_line})},
            target_file=target_file,
        )

    @classmethod
    def for_paths(
        cls,
        paths: Iterable[str],
        *,
        target_file: str = "",
        pre_covered: Mapping[str, frozenset[int]] | None = None,
    ) -> CoverageScope:
        """Build a multi-file scope from explicit source paths.

        ``executable_lines`` is auto-computed for each path via
        coverage.py's static analyzer. Files that fail to analyze
        receive an empty line set — this doesn't prevent tracking;
        it just means the file contributes zero to ``total_lines``
        and is trivially "covered" for ``is_fully_covered()``.

        Args:
            paths: Absolute source file paths to track.
            target_file: Which file to treat as the narrow-view target
                for plugin snapshots. Defaults to the first path.
            pre_covered: Optional per-file pre-covered line sets.

        Raises:
            ValueError: if ``paths`` is empty.
        """
        paths_list = list(paths)
        if not paths_list:
            raise ValueError("for_paths requires at least one path")

        executable = {p: frozenset(_executable_statements(p)) for p in paths_list}
        return cls(
            files=frozenset(paths_list),
            executable_lines=executable,
            pre_covered=dict(pre_covered) if pre_covered else {},
            target_file=target_file or paths_list[0],
        )

    @property
    def total_lines(self) -> int:
        """Sum of executable lines across all scope files."""
        return sum(len(v) for v in self.executable_lines.values())
