"""Unit tests for the widened line tracer + CoverageData builder.

The tracer records executed lines across a caller-supplied set of
source files. When the engine runs a target under a wide scope, every
``sys.settrace`` line event from any scope file is recorded per-file;
events from files outside the scope (Python stdlib, unrelated
modules) are silently ignored.

The dictionary shape ``{file: set[int]}`` passes directly through
``lines_to_coverage_data`` to build a multi-file ``CoverageData``
object, which then feeds the multi-file ``CoverageTracker``.
"""

from __future__ import annotations

import importlib.util
import time

from coverage import CoverageData

from pyct.engine.line_tracer import line_tracer, lines_to_coverage_data


def _load_module_from_file(path):
    spec = importlib.util.spec_from_file_location("fixture_mod", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestLineTracerFileFiltering:
    def test_single_file_in_scope_records_executed_lines(self, tmp_path):
        src = tmp_path / "a.py"
        src.write_text("def f():\n    x = 1\n    return x\n")
        mod = _load_module_from_file(str(src))

        with line_tracer(frozenset({str(src)})) as hits:
            mod.f()

        # Lines 2 and 3 fire; line 1 is the def, not a line event inside the call
        assert hits[str(src)] >= {2, 3}

    def test_multiple_files_captured_per_file(self, tmp_path):
        a_src = tmp_path / "a.py"
        a_src.write_text("from b import g\n\ndef f():\n    return g()\n")
        b_src = tmp_path / "b.py"
        b_src.write_text("def g():\n    x = 1\n    return x\n")

        import sys as _sys

        _sys.path.insert(0, str(tmp_path))
        try:
            mod = _load_module_from_file(str(a_src))
            with line_tracer(frozenset({str(a_src), str(b_src)})) as hits:
                mod.f()

            # Both files traced independently
            assert hits[str(a_src)]  # f() ran
            assert hits[str(b_src)]  # g() ran inside f
        finally:
            _sys.path.remove(str(tmp_path))

    def test_files_outside_scope_are_ignored(self, tmp_path):
        a_src = tmp_path / "a.py"
        a_src.write_text("from b import g\n\ndef f():\n    return g()\n")
        b_src = tmp_path / "b.py"
        b_src.write_text("def g():\n    return 1\n")

        import sys as _sys

        _sys.path.insert(0, str(tmp_path))
        try:
            mod = _load_module_from_file(str(a_src))
            # Scope restricted to a.py only — b.py must be silently ignored
            with line_tracer(frozenset({str(a_src)})) as hits:
                mod.f()

            assert str(a_src) in hits
            assert str(b_src) not in hits
        finally:
            _sys.path.remove(str(tmp_path))

    def test_yielded_dict_has_entry_per_scope_file(self, tmp_path):
        a_src = tmp_path / "a.py"
        a_src.write_text("def f():\n    return 1\n")
        b_src = tmp_path / "b.py"
        b_src.write_text("# empty\n")

        mod = _load_module_from_file(str(a_src))
        with line_tracer(frozenset({str(a_src), str(b_src)})) as hits:
            mod.f()

        # Both files keyed — b.py has an empty set (never executed)
        assert set(hits.keys()) == {str(a_src), str(b_src)}
        assert hits[str(b_src)] == set()


class TestLineTracerDeadline:
    def test_deadline_raises_timeout_error_in_traced_frame(self, tmp_path):
        src = tmp_path / "slow.py"
        # Target spins long enough that the deadline should fire.
        src.write_text(
            "def slow():\n"
            "    total = 0\n"
            "    for i in range(10_000_000):\n"
            "        total += i\n"
            "    return total\n"
        )
        mod = _load_module_from_file(str(src))

        raised = False
        try:
            deadline = time.monotonic() + 0.05
            with line_tracer(frozenset({str(src)}), deadline=deadline):
                mod.slow()
        except TimeoutError:
            raised = True
        assert raised


class TestLinesToCoverageData:
    def test_multi_file_dict_produces_multi_file_coverage_data(self, tmp_path):
        a_src = str(tmp_path / "a.py")
        b_src = str(tmp_path / "b.py")

        data = lines_to_coverage_data({a_src: {1, 2, 3}, b_src: {4, 5}})

        assert isinstance(data, CoverageData)
        assert sorted(data.lines(a_src) or []) == [1, 2, 3]
        assert sorted(data.lines(b_src) or []) == [4, 5]

    def test_empty_dict_produces_empty_coverage_data(self):
        data = lines_to_coverage_data({})
        assert isinstance(data, CoverageData)

    def test_file_with_empty_lines_set_not_added(self, tmp_path):
        # A file in scope that never executed shouldn't produce a
        # spurious empty-lines entry (coverage.py treats missing file
        # and zero-lines file differently in downstream analysis).
        a_src = str(tmp_path / "a.py")
        data = lines_to_coverage_data({a_src: set()})
        assert not data.lines(a_src)
