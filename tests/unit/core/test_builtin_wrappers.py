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


class TestConcolicWithoutHelperWarns:
    """A Concolic subclass missing to_int/to_str should NOT silently drop
    symbolic tracking. The whole point of this module is to stop the
    silent-drop pattern, so a subclass bug surfaces as a warning."""

    def test_int_wrapper_warns_when_concolic_lacks_to_int(self, caplog):
        import logging

        from pyct.core import Concolic
        from pyct.core.builtin_wrappers import _int

        class _StubConcolic(Concolic):
            def __init__(self, value):
                self._value = value

            def __int__(self):
                return self._value

        stub = _StubConcolic(7)
        with caplog.at_level(logging.WARNING, logger="ct.core.builtin_wrappers"):
            result = _int(stub)

        assert result == 7
        assert any("to_int" in r.message for r in caplog.records)

    def test_str_wrapper_warns_when_concolic_lacks_to_str(self, caplog):
        import logging

        from pyct.core import Concolic
        from pyct.core.builtin_wrappers import _str

        class _StubConcolic(Concolic):
            def __init__(self, value):
                self._value = value

            def __str__(self):
                return str(self._value)

        stub = _StubConcolic(42)
        with caplog.at_level(logging.WARNING, logger="ct.core.builtin_wrappers"):
            result = _str(stub)

        assert result == "42"
        assert any("to_str" in r.message for r in caplog.records)


class TestIsWrapper:
    def test_none_check_identity(self):
        from pyct.core.builtin_wrappers import _is

        assert _is(None, None) is True
        assert _is(1, None) is False

    def test_concolic_none_check_matches_plain_is(self):
        """The common ``x is None`` pattern must work with concolic ``x``.

        ``_is`` unwraps the concolic side before comparing identity against
        None. A concolic wrapper never unwraps to None, so the result is
        False — matching what a plain ``x is None`` would do on a non-None
        value."""
        from pyct.core.builtin_wrappers import _is
        from pyct.core.int import ConcolicInt

        ci = ConcolicInt(0, "x_VAR")
        assert _is(ci, None) is False

    def test_plain_identity_falls_through_to_python_is(self):
        """When neither operand is Concolic, ``_is`` must preserve Python's
        genuine object-identity semantics. Distinct list objects with the
        same contents are NOT identical — ``_is`` must not unwrap and
        compare by value."""
        from pyct.core.builtin_wrappers import _is

        list_a: list[int] = [1, 2, 3]
        list_b: list[int] = [1, 2, 3]
        assert _is(list_a, list_a) is True
        assert _is(list_a, list_b) is False  # distinct objects, same content

    def test_concolic_vs_none_is_false(self):
        """A Concolic wrapper compared to None must unwrap to return False,
        matching the source-level meaning of ``x is None`` when x was a
        concolic input (it was always a primitive, never None)."""
        from pyct.core.builtin_wrappers import _is
        from pyct.core.str.str import ConcolicStr

        cs = ConcolicStr("hello", "s_VAR")
        assert _is(cs, None) is False

    def test_is_returns_bool(self):
        from pyct.core.builtin_wrappers import _is

        result = _is("a", "b")
        assert isinstance(result, bool)
