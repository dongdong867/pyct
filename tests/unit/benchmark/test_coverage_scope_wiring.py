"""Unit tests for benchmark coverage-scope wiring.

The benchmark CLI exposes ``--coverage-scope {narrow,wide}`` to control
whether the concolic engine tracks coverage only within the target
function's own file (narrow, classical) or across the target's whole
package directory (wide). This module tests the plumbing:
BenchmarkConfig has a default, and ``_build_coverage_scope`` maps
target + config to either a CoverageScope or None.

Integration with the live engine is covered by the in-repo regression
suite in ``tests/unit/engine/test_scope_termination.py``.
"""

from __future__ import annotations

import textwrap

import pytest
from tools.benchmark.models import BenchmarkConfig
from tools.benchmark.runners import _build_coverage_scope
from tools.benchmark.targets import BenchmarkTarget

from pyct.engine.coverage_scope import CoverageScope


def _write_package(root, name, modules):
    """Build a package directory with the given module names."""
    pkg = root / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    for mod, body in modules.items():
        (pkg / f"{mod}.py").write_text(textwrap.dedent(body))
    return str(pkg)


class TestBenchmarkConfigCoverageScopeDefault:
    def test_default_is_wide(self):
        # Wide is the friendlier default for routine benchmark runs:
        # standard suite targets (no source_path) degrade to narrow
        # automatically, while library + realworld targets benefit from
        # the engine exploring past thin-wrapper boundaries.
        config = BenchmarkConfig()
        assert config.coverage_scope == "wide"

    def test_coverage_scope_accepted_as_narrow(self):
        config = BenchmarkConfig(coverage_scope="narrow")
        assert config.coverage_scope == "narrow"

    def test_coverage_scope_is_in_dict_serialization(self):
        config = BenchmarkConfig(coverage_scope="narrow")
        assert config.to_dict()["coverage_scope"] == "narrow"


class TestBuildCoverageScope:
    @pytest.fixture
    def target_with_source_path(self, tmp_path):
        pkg_path = _write_package(
            tmp_path,
            "mypkg",
            {
                "main": "def f(x):\n    return x + 1\n",
                "helper": "def g(x):\n    if x > 0:\n        return 'pos'\n    return 'np'\n",
            },
        )
        return BenchmarkTarget(
            name="target",
            module="mypkg.main",
            function="f",
            source_path=pkg_path,
        )

    @pytest.fixture
    def target_without_source_path(self):
        return BenchmarkTarget(
            name="target",
            module="examples.string_constraints.email_validation",
            function="email_validation",
        )

    def test_narrow_returns_none_for_source_backed_target(self, target_with_source_path):
        config = BenchmarkConfig(coverage_scope="narrow")
        assert _build_coverage_scope(target_with_source_path, config) is None

    def test_narrow_returns_none_for_standard_target(self, target_without_source_path):
        config = BenchmarkConfig(coverage_scope="narrow")
        assert _build_coverage_scope(target_without_source_path, config) is None

    def test_wide_returns_none_when_no_source_path(self, target_without_source_path):
        # Without source_path we have no package to expand into, so "wide"
        # degrades to narrow — engine builds a single-file scope by default.
        config = BenchmarkConfig(coverage_scope="wide")
        assert _build_coverage_scope(target_without_source_path, config) is None

    def test_wide_returns_scope_covering_all_package_files(self, target_with_source_path):
        config = BenchmarkConfig(coverage_scope="wide")
        scope = _build_coverage_scope(target_with_source_path, config)

        assert isinstance(scope, CoverageScope)
        # Both main.py and helper.py from the fake package are tracked
        file_basenames = {p.split("/")[-1] for p in scope.files}
        assert "main.py" in file_basenames
        assert "helper.py" in file_basenames

    def test_wide_scope_executable_lines_populated(self, target_with_source_path):
        config = BenchmarkConfig(coverage_scope="wide")
        scope = _build_coverage_scope(target_with_source_path, config)

        assert scope is not None
        assert scope.total_lines > 0
