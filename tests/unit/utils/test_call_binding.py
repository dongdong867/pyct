"""Unit tests for call_with_args — the argument-binding helper.

The helper exists because ``func(**args)`` cannot deliver values to
positional-only parameters. Every site that invokes a user-provided
target from a seed dict (benchmark runners, engine iteration, LLM
plugin seed application) must go through this helper so that targets
like ``validators.url(value: str, /, *, ...)`` actually receive
``value`` positionally.

Secondary responsibility: sanitize seed dicts so LLM-generated junk
(non-callable values for ``Callable``-annotated params, extra keys
not in the signature) falls back to the target's defaults instead of
poisoning the call.
"""

from __future__ import annotations

from collections.abc import Callable


def _positional_only(value: str, /, *, flag: bool = False) -> tuple[str, bool]:
    return value, flag


def _mixed(a: int, b: int = 0, /, c: int = 0, *, d: int = 0) -> tuple[int, int, int, int]:
    # a, b are positional-only; c is positional-or-keyword; d is keyword-only
    return a, b, c, d


def _default_scheme(s: str) -> bool:
    return s == "http"


def _with_callable_default(
    value: str, /, *, validate: Callable[[str], bool] = _default_scheme
) -> bool:
    return validate(value)


class TestPositionalOnlyBinding:
    def test_positional_only_value_is_passed_positionally(self):
        from pyct.utils.call_binding import call_with_args

        result = call_with_args(_positional_only, {"value": "hello"})

        assert result == ("hello", False)

    def test_positional_only_and_keyword_only_both_bind(self):
        from pyct.utils.call_binding import call_with_args

        result = call_with_args(_positional_only, {"value": "hi", "flag": True})

        assert result == ("hi", True)

    def test_mixed_kinds_bind_correctly(self):
        from pyct.utils.call_binding import call_with_args

        result = call_with_args(_mixed, {"a": 1, "b": 2, "c": 3, "d": 4})

        assert result == (1, 2, 3, 4)

    def test_positional_only_preserves_ordering_when_dict_order_differs(self):
        from pyct.utils.call_binding import call_with_args

        # Dict key order shouldn't affect positional-only binding; the
        # helper must use signature order, not dict iteration order.
        result = call_with_args(_mixed, {"d": 4, "b": 2, "c": 3, "a": 1})

        assert result == (1, 2, 3, 4)


class TestExtraKeyFiltering:
    def test_keys_not_in_signature_are_dropped(self):
        from pyct.utils.call_binding import call_with_args

        # ``ghost`` is not a parameter of _positional_only — must not
        # raise ``TypeError: unexpected keyword argument``.
        result = call_with_args(_positional_only, {"value": "x", "flag": True, "ghost": 99})

        assert result == ("x", True)


class TestCallableAnnotationSanitization:
    def test_non_callable_value_for_callable_param_falls_back_to_default(self):
        from pyct.utils.call_binding import call_with_args

        # LLM generated ``"validate": None`` for a Callable-annotated
        # param. The helper must drop this key so Python uses the
        # target's real default callable.
        result = call_with_args(_with_callable_default, {"value": "http", "validate": None})

        assert result is True  # default _default_scheme("http") -> True

    def test_callable_value_for_callable_param_passes_through(self):
        from pyct.utils.call_binding import call_with_args

        def always_false(_s: str) -> bool:
            return False

        result = call_with_args(_with_callable_default, {"value": "http", "validate": always_false})

        assert result is False
