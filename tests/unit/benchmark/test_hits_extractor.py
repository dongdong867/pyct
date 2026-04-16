"""Extract normalized hits from a coverage.py data object.

The adapter turns coverage.py's absolute-path measured-files view into
the ``{normalized_path: {lines}}`` shape that ``measure_against_baseline``
consumes. Paths outside site-packages are dropped (editable installs,
examples, test fixtures — none of which appear in library baselines).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tools.benchmark.baseline import hits_from_coverage_data


@dataclass
class _FakeData:
    """Minimal duck-typed stand-in for coverage.CoverageData."""

    files: dict[str, list[int]] = field(default_factory=dict)

    def measured_files(self) -> list[str]:
        return list(self.files.keys())

    def lines(self, path: str) -> list[int] | None:
        return self.files.get(path)


def test_hits_extracted_and_normalized_for_site_packages_file():
    data = _FakeData(
        {
            "/v/lib/python3.12/site-packages/yaml/__init__.py": [10, 12, 15],
        }
    )

    hits = hits_from_coverage_data(data)

    assert hits == {"yaml/__init__.py": {10, 12, 15}}


def test_hits_extractor_merges_multiple_site_packages_files():
    data = _FakeData(
        {
            "/v/lib/python3.12/site-packages/yaml/__init__.py": [10, 12],
            "/v/lib/python3.12/site-packages/yaml/loader.py": [1, 2, 3],
        }
    )

    hits = hits_from_coverage_data(data)

    assert hits == {
        "yaml/__init__.py": {10, 12},
        "yaml/loader.py": {1, 2, 3},
    }


def test_hits_extractor_drops_paths_outside_site_packages():
    data = _FakeData(
        {
            "/v/lib/python3.12/site-packages/yaml/__init__.py": [10],
            "/Users/dong/dev/pyct/src/pyct/engine.py": [1, 2],
        }
    )

    hits = hits_from_coverage_data(data)

    assert hits == {"yaml/__init__.py": {10}}


def test_hits_extractor_skips_files_with_no_hits():
    # coverage.py can report a measured file with an empty line list
    # (e.g., a file registered but never executed). Such files add
    # nothing to the denominator comparison and are dropped.
    data = _FakeData(
        {
            "/v/lib/python3.12/site-packages/yaml/__init__.py": [],
            "/v/lib/python3.12/site-packages/yaml/loader.py": [5],
        }
    )

    hits = hits_from_coverage_data(data)

    assert hits == {"yaml/loader.py": {5}}


def test_hits_extractor_handles_none_from_lines_call():
    # coverage.py's CoverageData.lines() can return None if a file was
    # measured but has no recorded line data — must not crash.
    class _NoneLinesData:
        def measured_files(self):
            return ["/v/lib/python3.12/site-packages/yaml/__init__.py"]

        def lines(self, path):  # noqa: ARG002
            return None

    hits = hits_from_coverage_data(_NoneLinesData())

    assert hits == {}


def test_hits_extractor_returns_empty_for_no_measured_files():
    hits = hits_from_coverage_data(_FakeData())

    assert hits == {}
