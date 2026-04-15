"""Unit tests for the prepared_environment() context manager.

These tests lock in the save/restore semantics of the environment
patches independent of engine wiring. Acceptance tests in
``tests/acceptance/test_builtins.py`` exercise the patches through the
engine; these unit tests catch bugs in the helper itself.

Tests cover:
- Happy: each patch is installed inside the block and reverted after.
- Error: exception inside the block still restores every patch.
- Discriminating: ``builtins.len(ConcolicStr)`` returns a ConcolicInt
  carrying the ``str.len`` symbolic expression inside the context.
"""

from __future__ import annotations

import builtins
import socket
import sys

import pytest


@pytest.fixture
def saved_state():
    """Snapshot the three environment variables we patch.

    Returns ``(original_len, original_getaddrinfo, original_limit)``.
    Pytest doesn't auto-restore module-level attributes, so any
    mis-behaving test that leaves them mutated would pollute the suite
    — this fixture gives us a clean baseline to assert against.
    """
    return builtins.len, socket.getaddrinfo, sys.getrecursionlimit()


class TestPreparedEnvironmentHappy:
    def test_len_replaced_inside_block(self, saved_state):
        from pyct.engine.environment import prepared_environment

        original_len, _, _ = saved_state
        with prepared_environment():
            assert builtins.len is not original_len

    def test_len_restored_after_block(self, saved_state):
        from pyct.engine.environment import prepared_environment

        original_len, _, _ = saved_state
        with prepared_environment():
            pass
        assert builtins.len is original_len

    def test_recursion_limit_bumped_inside_block(self, saved_state):
        from pyct.engine.environment import prepared_environment

        with prepared_environment():
            assert sys.getrecursionlimit() >= 1_000_000

    def test_recursion_limit_restored_after_block(self, saved_state):
        from pyct.engine.environment import prepared_environment

        _, _, original_limit = saved_state
        with prepared_environment():
            pass
        assert sys.getrecursionlimit() == original_limit

    def test_socket_getaddrinfo_wrapped_inside_block(self, saved_state):
        from pyct.engine.environment import prepared_environment

        _, original_getaddrinfo, _ = saved_state
        with prepared_environment():
            assert socket.getaddrinfo is not original_getaddrinfo

    def test_socket_getaddrinfo_restored_after_block(self, saved_state):
        from pyct.engine.environment import prepared_environment

        _, original_getaddrinfo, _ = saved_state
        with prepared_environment():
            pass
        assert socket.getaddrinfo is original_getaddrinfo


class TestPreparedEnvironmentError:
    def test_len_restored_after_exception(self, saved_state):
        from pyct.engine.environment import prepared_environment

        original_len, _, _ = saved_state
        with pytest.raises(RuntimeError, match="boom"), prepared_environment():
            raise RuntimeError("boom")
        assert builtins.len is original_len

    def test_recursion_limit_restored_after_exception(self, saved_state):
        from pyct.engine.environment import prepared_environment

        _, _, original_limit = saved_state
        with pytest.raises(RuntimeError), prepared_environment():
            raise RuntimeError("boom")
        assert sys.getrecursionlimit() == original_limit

    def test_socket_restored_after_exception(self, saved_state):
        from pyct.engine.environment import prepared_environment

        _, original_getaddrinfo, _ = saved_state
        with pytest.raises(RuntimeError), prepared_environment():
            raise RuntimeError("boom")
        assert socket.getaddrinfo is original_getaddrinfo


class TestLenReturnsConcolicInt:
    def test_len_concolic_str_returns_concolic_int_with_symbolic_expr(self, engine):
        """The load-bearing property that legacy lost and we fixed:
        inside the context, ``len(concolic_str)`` returns a ConcolicInt
        whose expression is ``["str.len", <the_concolic_str>]``.

        Without the monkey-patch, CPython's ``PyObject_Size`` unwraps
        the ConcolicInt into a raw int, stripping the symbolic link —
        the branch on ``len(s) == 0`` then never fires, and the engine
        sees no length constraint. This test discriminates real
        symbolic tracking from a no-op patch.
        """
        from pyct.core.int import ConcolicInt
        from pyct.core.str.str import ConcolicStr
        from pyct.engine.environment import prepared_environment

        cs = ConcolicStr("hello", "s_VAR", engine)
        with prepared_environment():
            result = len(cs)
            assert isinstance(result, ConcolicInt)
            assert result.expr == ["str.len", cs]
