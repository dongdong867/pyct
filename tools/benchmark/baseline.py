"""Frozen baselines — shared denominator for library/realworld coverage.

A baseline fixes the set of source lines a target's coverage is measured
against, so every runner on a given target shares the same denominator.
Baselines are generated once by exercising the target broadly, then
committed to git for reviewability and reproducibility.

The measurement function here is pure: it takes a mapping of
``file -> hit line set`` and a :class:`Baseline`, and computes a
:class:`CoverageResult`. The coverage.py integration (session →
hits mapping) lives with the runner wiring, not here.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.benchmark.models import CoverageResult

BASELINE_SCHEMA_VERSION = "1"

_SITE_PACKAGES = "site-packages"


@dataclass(frozen=True)
class FunctionScope:
    """Executable lines of a single entered function.

    ``lines`` includes the def/decorator header and every executable
    body statement — the same set coverage.py's static analysis reports
    for the function's source range. Stored as a tuple for hashability
    and JSON-friendly serialization.
    """

    file: str
    start_line: int
    end_line: int
    lines: tuple[int, ...]


@dataclass(frozen=True)
class Baseline:
    """Frozen coverage scope for a single benchmark target."""

    target: str
    scopes: tuple[FunctionScope, ...]
    generated_at: str
    generator_version: str

    @property
    def total_lines(self) -> int:
        return sum(len(s.lines) for s in self.scopes)

    def to_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._to_dict(), indent=2) + "\n")

    @classmethod
    def from_json(cls, path: Path) -> Baseline:
        payload = json.loads(path.read_text())
        return cls._from_dict(payload)

    def _to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "generated_at": self.generated_at,
            "generator_version": self.generator_version,
            "scopes": [
                {
                    "file": s.file,
                    "start_line": s.start_line,
                    "end_line": s.end_line,
                    "lines": list(s.lines),
                }
                for s in self.scopes
            ],
        }

    @classmethod
    def _from_dict(cls, payload: dict[str, Any]) -> Baseline:
        scopes = tuple(
            FunctionScope(
                file=s["file"],
                start_line=s["start_line"],
                end_line=s["end_line"],
                lines=tuple(s["lines"]),
            )
            for s in payload["scopes"]
        )
        return cls(
            target=payload["target"],
            scopes=scopes,
            generated_at=payload["generated_at"],
            generator_version=payload["generator_version"],
        )


def build_baseline(
    target_name: str,
    per_run_scope_lists: Sequence[list[FunctionScope]],
    now: datetime,
) -> Baseline:
    """Compose per-run scope lists into a finished :class:`Baseline`.

    Steps: normalize each run's paths to site-packages-relative form
    (dropping out-of-scope files), union the runs, stamp with target
    name + ISO timestamp + schema version. Scopes end up sorted by
    ``(file, start_line)`` for stable JSON diffs.
    """
    normalized_lists = [normalize_scope_paths(scopes) for scopes in per_run_scope_lists]
    merged = merge_scopes(*normalized_lists)
    return Baseline(
        target=target_name,
        scopes=merged,
        generated_at=now.isoformat(timespec="seconds"),
        generator_version=BASELINE_SCHEMA_VERSION,
    )


def measure_against_baseline(
    hits: dict[str, set[int]],
    baseline: Baseline,
) -> CoverageResult:
    """Score ``hits`` against the baseline's frozen line scope.

    For each :class:`FunctionScope`, count in-scope hits and — when any
    body line was hit — backfill def/decorator lines before the first
    hit (coverage.py reports those as executed only at import time).
    Hits outside any scope are ignored; backfill does not cross scope
    boundaries.
    """
    total = baseline.total_lines
    if total == 0:
        return CoverageResult(
            coverage_percent=0.0,
            executed_lines=0,
            total_lines=0,
            executed_line_numbers=[],
            missing_line_numbers=[],
        )

    covered_total = 0
    for scope in baseline.scopes:
        covered_total += _covered_in_scope(scope, hits.get(scope.file, set()))

    pct = covered_total / total * 100
    return CoverageResult(
        coverage_percent=pct,
        executed_lines=covered_total,
        total_lines=total,
        executed_line_numbers=[],
        missing_line_numbers=[],
    )


def normalize_to_site_packages_relative(abs_path: str) -> str | None:
    """Return the ``site-packages/``-relative suffix of an absolute path.

    Benchmarks run against packages installed in a venv, so
    ``site-packages/`` always separates install-location noise from the
    package-relative path we want to freeze. Returns ``None`` when the
    path is not under a ``site-packages`` directory (editable installs,
    source trees, test fixtures).

    Uses the LAST ``site-packages`` component in the path so nested
    bundled tools resolve to the true install location.
    """
    if not abs_path:
        return None

    parts = abs_path.split("/")
    last_match = -1
    for i, part in enumerate(parts):
        if part == _SITE_PACKAGES:
            last_match = i

    if last_match < 0 or last_match == len(parts) - 1:
        return None

    return "/".join(parts[last_match + 1 :])


def function_scopes_in_source(
    source: str,
    executable: set[int],
    hit: set[int],
    file_key: str,
) -> list[FunctionScope]:
    """Emit one :class:`FunctionScope` per entered function in ``source``.

    A function is *entered* when at least one of its executable lines
    was hit. Each emitted scope's ``lines`` holds every executable line
    within the function's source range — not just the hit ones —
    because the scope IS the denominator. Module-level statements are
    never emitted (they run uniformly at import time and would dilute
    the metric). Syntax errors in ``source`` yield an empty list.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    scopes: list[FunctionScope] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = node.lineno
        end = getattr(node, "end_lineno", None) or start
        scope_exec = executable & set(range(start, end + 1))
        if not (scope_exec & hit):
            continue
        scopes.append(
            FunctionScope(
                file=file_key,
                start_line=start,
                end_line=end,
                lines=tuple(sorted(scope_exec)),
            )
        )
    return scopes


def scopes_from_coverage_session(cov: Any) -> list[FunctionScope]:
    """Walk every measured file and collect entered function scopes.

    Uses coverage.py's real API — ``cov.get_data()`` for measurement
    data, ``cov.analysis(path)`` for the executable-statement set.
    Returned scopes preserve absolute file paths so test fixtures under
    ``tmp_path`` can exercise this function without pretending to live
    under site-packages; callers apply :func:`normalize_scope_paths`
    before unioning or serializing. Files that cannot be read (stale
    paths, permissions) are skipped silently so one unreadable file
    does not sink an entire baseline run.
    """
    data = cov.get_data()
    scopes: list[FunctionScope] = []
    for abs_path in data.measured_files():
        try:
            source = Path(abs_path).read_text()
        except OSError:
            continue
        _, statements, _, _ = cov.analysis(abs_path)
        executable = set(statements)
        hit = set(data.lines(abs_path) or [])
        scopes.extend(function_scopes_in_source(source, executable, hit, abs_path))
    return scopes


def normalize_scope_paths(scopes: list[FunctionScope]) -> list[FunctionScope]:
    """Rewrite scope file paths to site-packages-relative form.

    Scopes whose file is not under a ``site-packages`` directory are
    dropped — only callees inside installed packages belong in the
    baseline.
    """
    result: list[FunctionScope] = []
    for scope in scopes:
        key = normalize_to_site_packages_relative(scope.file)
        if key is None:
            continue
        result.append(
            FunctionScope(
                file=key,
                start_line=scope.start_line,
                end_line=scope.end_line,
                lines=scope.lines,
            )
        )
    return result


def merge_scopes(*scope_lists: list[FunctionScope]) -> tuple[FunctionScope, ...]:
    """Dedupe and sort scopes from any number of runs.

    Scopes are value-compared (frozen dataclass), so identical entries
    across runs collapse automatically. Result is sorted by
    ``(file, start_line)`` for stable JSON output and easy diffing.
    """
    unique: set[FunctionScope] = set()
    for scopes in scope_lists:
        unique.update(scopes)
    return tuple(sorted(unique, key=lambda s: (s.file, s.start_line)))


def hits_from_coverage_data(data: Any) -> dict[str, set[int]]:
    """Extract normalized hits from a coverage.py ``CoverageData``.

    Accepts any duck-typed object exposing ``measured_files()`` and
    ``lines(path)``. Paths outside ``site-packages`` are dropped, as are
    files with no recorded lines.
    """
    hits: dict[str, set[int]] = {}
    for abs_path in data.measured_files():
        key = normalize_to_site_packages_relative(abs_path)
        if key is None:
            continue
        raw = data.lines(abs_path)
        if not raw:
            continue
        hits[key] = set(raw)
    return hits


def _covered_in_scope(scope: FunctionScope, file_hits: set[int]) -> int:
    """Count covered lines within one scope, with def-line backfill.

    Returns 0 if no scope line was hit. Otherwise, every line in the
    scope prior to the first hit is treated as covered (the def header
    ran at import time, not at call time — coverage.py won't see it).
    """
    scope_set = set(scope.lines)
    in_scope_hits = scope_set & file_hits
    if not in_scope_hits:
        return 0

    first_hit = min(in_scope_hits)
    backfilled = {ln for ln in scope_set if ln < first_hit}
    return len(in_scope_hits | backfilled)
