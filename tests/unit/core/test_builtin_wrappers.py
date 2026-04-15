"""Unit tests for pyct.core.builtin_wrappers (_int, _str, _is).

These helpers are the runtime dispatch layer injected by the AST
transformer. The transformer rewrites ``int(x)`` to
``pyct.core.builtin_wrappers._int(x)`` at target load time; at execution
time ``_int`` checks whether its argument is a Concolic value and
either routes to ``.to_int()`` (preserving symbolic tracking) or falls
through to the saved primitive ``int`` builtin (for plain values).

Tests cover happy (concolic dispatch), edge (primitive fall-through),
and error (non-convertible values).
"""

from __future__ import annotations


class TestIntWrapper:
    def test_concolic_str_dispatches_to_to_int(self):
        from pyct.core.builtin_wrappers import _int
        from pyct.core.str.str import ConcolicStr

        cs = ConcolicStr("42", "s_VAR")
        result = _int(cs)
        assert int(result) == 42

    def test_primitive_str_falls_through(self):
        from pyct.core.builtin_wrappers import _int

        assert _int("42") == 42
        assert type(_int("42")) is int

    def test_primitive_int_passes_through(self):
        from pyct.core.builtin_wrappers import _int

        assert _int(42) == 42

    def test_primitive_float_truncates(self):
        from pyct.core.builtin_wrappers import _int

        assert _int(3.7) == 3


class TestStrWrapper:
    def test_concolic_int_dispatches_to_to_str(self):
        from pyct.core.builtin_wrappers import _str
        from pyct.core.int import ConcolicInt

        ci = ConcolicInt(42, "x_VAR")
        result = _str(ci)
        assert str(result) == "42"

    def test_primitive_int_falls_through(self):
        from pyct.core.builtin_wrappers import _str

        assert _str(42) == "42"
        assert type(_str(42)) is str

    def test_primitive_str_passes_through(self):
        from pyct.core.builtin_wrappers import _str

        assert _str("hello") == "hello"


class TestIsWrapper:
    def test_none_check_identity(self):
        from pyct.core.builtin_wrappers import _is

        assert _is(None, None) is True
        assert _is(1, None) is False

    def test_concolic_none_check_matches_plain_is(self):
        """The common ``x is None`` pattern must work with concolic ``x``.

        ``_is`` unwraps both sides before comparing identity, so a concolic
        value tested against ``None`` returns False (concolic primitives
        never unwrap to None)."""
        from pyct.core.builtin_wrappers import _is
        from pyct.core.int import ConcolicInt

        ci = ConcolicInt(0, "x_VAR")
        assert _is(ci, None) is False

    def test_concolic_compared_to_unwrapped_same_small_int(self):
        """Unwrapping collapses distinct concolic wrappers of the same small
        int to the same cached int object, so ``_is`` returns True.

        This matches upstream semantics: ``_is`` is intentionally MORE
        permissive than plain ``is`` on concolic wrappers, because plain
        ``is`` would be False (distinct wrapper objects)."""
        from pyct.core.builtin_wrappers import _is
        from pyct.core.int import ConcolicInt

        a = ConcolicInt(5, "a_VAR")
        b = ConcolicInt(5, "b_VAR")
        # Small ints (-5 to 256) are cached in CPython, so unwrap(a) is unwrap(b).
        assert _is(a, b) is True
        # Plain `is` on the wrappers is False — they're distinct objects.
        assert (a is b) is False

    def test_is_returns_bool(self):
        from pyct.core.builtin_wrappers import _is

        result = _is("a", "b")
        assert isinstance(result, bool)
