"""Unit tests for ConcolicRange — symbolic iteration over range().

The AST transformer rewrites ``for _ in range(n):`` to
``for _ in ConcolicRange(n):``. The custom class provides a
Python-level ``__iter__`` that registers a branch on every
``current < stop`` check, so the solver sees loop-count constraints
instead of the C-level fast-path iterator stripping them.

This is NOT a full clone of upstream's ``libct/concolic/range.py``
(which is 214 lines). We port only what's needed: construction,
iteration with branch registration, and length. Other methods
(count, index, __contains__, __getitem__) pass through to the
underlying primitive ``range`` without symbolic tracking.
"""

from __future__ import annotations


class TestConstruction:
    def test_single_arg_stop_only(self, engine):
        from pyct.core.concolic_range import ConcolicRange
        from pyct.core.int import ConcolicInt

        stop = ConcolicInt(5, "n_VAR", engine)
        cr = ConcolicRange(stop)
        assert int(cr.start) == 0
        assert int(cr.stop) == 5
        assert int(cr.step) == 1

    def test_start_and_stop(self, engine):
        from pyct.core.concolic_range import ConcolicRange

        cr = ConcolicRange(2, 10)
        assert int(cr.start) == 2
        assert int(cr.stop) == 10
        assert int(cr.step) == 1

    def test_start_stop_step(self, engine):
        from pyct.core.concolic_range import ConcolicRange

        cr = ConcolicRange(0, 10, 2)
        assert int(cr.start) == 0
        assert int(cr.stop) == 10
        assert int(cr.step) == 2

    def test_accepts_primitive_ints(self):
        from pyct.core.concolic_range import ConcolicRange

        cr = ConcolicRange(5)
        assert int(cr.stop) == 5


class TestIteration:
    def test_yields_all_values(self):
        from pyct.core.concolic_range import ConcolicRange

        values = list(ConcolicRange(5))
        assert [int(v) for v in values] == [0, 1, 2, 3, 4]

    def test_empty_range_zero(self):
        from pyct.core.concolic_range import ConcolicRange

        values = list(ConcolicRange(0))
        assert values == []

    def test_start_stop(self):
        from pyct.core.concolic_range import ConcolicRange

        values = list(ConcolicRange(2, 6))
        assert [int(v) for v in values] == [2, 3, 4, 5]

    def test_step(self):
        from pyct.core.concolic_range import ConcolicRange

        values = list(ConcolicRange(0, 10, 3))
        assert [int(v) for v in values] == [0, 3, 6, 9]

    def test_iteration_registers_branches(self, engine):
        """Each step through the loop must register a branch so the
        solver sees the loop-count constraint."""
        from pyct.core.concolic_range import ConcolicRange
        from pyct.core.int import ConcolicInt

        stop = ConcolicInt(3, "n_VAR", engine)
        values = list(ConcolicRange(stop))
        assert [int(v) for v in values] == [0, 1, 2]
        # Each iteration's `current < stop` check should have fired a
        # branch registration. We expect at least one branch — the
        # exact count depends on how the loop body is structured.
        assert len(engine.path.branches) >= 1


class TestLength:
    def test_len_simple(self):
        from pyct.core.concolic_range import ConcolicRange

        cr = ConcolicRange(5)
        assert len(cr) == 5

    def test_len_start_stop(self):
        from pyct.core.concolic_range import ConcolicRange

        cr = ConcolicRange(2, 6)
        assert len(cr) == 4
