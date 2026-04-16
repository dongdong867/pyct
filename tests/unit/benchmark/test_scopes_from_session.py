"""Integration layer: coverage.py session → FunctionScope list.

Generating a baseline runs the target under coverage.py, then walks
every measured source file to extract entered function scopes. This
module tests the session adapter and the multi-run merge step.
The source-level extraction is tested in ``test_scope_extraction.py``;
here we focus on filesystem + session I/O and on union semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tools.benchmark.baseline import (
    FunctionScope,
    merge_scopes,
    normalize_scope_paths,
    scopes_from_coverage_session,
)


@dataclass
class _FakeData:
    """Stand-in for ``coverage.CoverageData`` (measured_files + lines)."""

    files: dict[str, dict[str, list[int]]]

    def measured_files(self) -> list[str]:
        return list(self.files.keys())

    def lines(self, path: str) -> list[int] | None:
        return sorted(self.files[path]["hit"])


@dataclass
class _FakeSession:
    """Stand-in for ``coverage.Coverage`` — exposes ``get_data`` + ``analysis``."""

    files: dict[str, dict[str, list[int]]] = field(default_factory=dict)

    def get_data(self) -> _FakeData:
        return _FakeData(self.files)

    def analysis(self, path: str) -> tuple[str, list[int], list[int], list[int]]:
        return path, sorted(self.files[path]["executable"]), [], []


# ── scopes_from_coverage_session ──────────────────────────────────


def test_session_scopes_read_source_and_preserve_absolute_paths(tmp_path):
    src_file = tmp_path / "m.py"
    # def foo(): line 1, return line 2, blank, def bar(): line 4, return line 5
    src_file.write_text("def foo():\n    return 1\n\ndef bar():\n    return 2\n")
    abs_path = str(src_file)
    session = _FakeSession({abs_path: {"executable": [1, 2, 4, 5], "hit": [1, 2]}})

    scopes = scopes_from_coverage_session(session)

    assert len(scopes) == 1
    assert scopes[0].file == abs_path
    assert scopes[0].start_line == 1
    assert scopes[0].lines == (1, 2)


def test_session_scopes_skip_files_that_cannot_be_read(tmp_path):
    # Session claims a file exists but the filesystem disagrees — must
    # skip silently rather than crash the entire baseline generation.
    ghost = str(tmp_path / "never_existed.py")
    session = _FakeSession({ghost: {"executable": [1], "hit": [1]}})

    scopes = scopes_from_coverage_session(session)

    assert scopes == []


def test_session_scopes_returns_empty_for_empty_session():
    assert scopes_from_coverage_session(_FakeSession()) == []


# ── normalize_scope_paths ─────────────────────────────────────────


def test_normalize_converts_absolute_to_site_packages_relative():
    scopes = [
        FunctionScope(
            file="/v/lib/python3.12/site-packages/yaml/__init__.py",
            start_line=1,
            end_line=5,
            lines=(1, 2, 3),
        ),
        FunctionScope(
            file="/v/lib/python3.12/site-packages/werkzeug/http.py",
            start_line=10,
            end_line=20,
            lines=(10, 11),
        ),
    ]

    normalized = normalize_scope_paths(scopes)

    files = sorted(s.file for s in normalized)
    assert files == ["werkzeug/http.py", "yaml/__init__.py"]


def test_normalize_drops_scopes_not_under_site_packages():
    scopes = [
        FunctionScope(
            file="/v/lib/python3.12/site-packages/yaml/__init__.py",
            start_line=1,
            end_line=5,
            lines=(1, 2, 3),
        ),
        FunctionScope(
            file="/Users/dong/dev/pyct/src/pyct/engine.py",
            start_line=1,
            end_line=5,
            lines=(1, 2, 3),
        ),
    ]

    normalized = normalize_scope_paths(scopes)

    assert len(normalized) == 1
    assert normalized[0].file == "yaml/__init__.py"


# ── merge_scopes ──────────────────────────────────────────────────


def test_merge_dedupes_identical_scopes_across_runs():
    # Two runners both entered the same function — scope should appear once.
    shared = FunctionScope("a.py", 1, 5, (1, 2, 3))

    merged = merge_scopes([shared], [shared])

    assert len(merged) == 1


def test_merge_preserves_distinct_scopes_in_same_file():
    s1 = FunctionScope("a.py", 1, 5, (1, 2, 3))
    s2 = FunctionScope("a.py", 10, 15, (10, 11, 12))

    merged = merge_scopes([s1], [s2])

    assert {(s.file, s.start_line) for s in merged} == {("a.py", 1), ("a.py", 10)}


def test_merge_returns_scopes_sorted_by_file_then_start_line():
    s_a_10 = FunctionScope("a.py", 10, 20, (10, 11))
    s_a_1 = FunctionScope("a.py", 1, 5, (1, 2))
    s_b_1 = FunctionScope("b.py", 1, 5, (1, 2))

    merged = merge_scopes([s_a_10], [s_b_1, s_a_1])

    assert [(s.file, s.start_line) for s in merged] == [
        ("a.py", 1),
        ("a.py", 10),
        ("b.py", 1),
    ]


def test_merge_handles_no_input_lists():
    assert merge_scopes() == ()


def test_merge_handles_empty_lists():
    assert merge_scopes([], []) == ()
