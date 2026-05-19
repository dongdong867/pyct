"""Unit tests for @pre / @post decorators + predicate compilation.

Task 2 scope: decorators populate __pyct_contracts__ with compiled
predicate, condition_args from co_names ∩ signature, eager
syntax-error reporting via PyCTContractSyntaxError, __return__ /
underscore normalization, source-line capture, and module surface
lockdown.
"""

from __future__ import annotations

import pytest

# Module-level constant used by the module-global resolution test —
# the predicate string ``"x > MIN_VAL"`` must resolve MIN_VAL via the
# target function's __globals__ at predicate eval time.
MIN_VAL = 0


def test_decorator_module_exports():
    from pyct.contracts import PyCTContractSyntaxError, post, pre

    assert callable(pre)
    assert callable(post)
    assert issubclass(PyCTContractSyntaxError, SyntaxError)


def test_module_all_lockdown():
    import pyct.contracts as contracts

    assert contracts.__all__ == (
        "pre",
        "post",
        "Contract",
        "ContractSet",
        "EMPTY_CONTRACTS",
        "discover_contracts",
        "PyCTContractSyntaxError",
    )


def test_pre_attaches_contract_set_preserving_identity():
    from pyct.contracts import ContractSet, pre

    def original(x):
        return x

    decorated = pre("x > 0")(original)

    assert decorated is original
    cs = decorated.__pyct_contracts__
    assert isinstance(cs, ContractSet)
    assert len(cs.requires) == 1
    assert cs.ensures == ()
    req = cs.requires[0]
    assert req.condition_args == ("x",)
    assert req.description == "x > 0"
    assert req.predicate(x=5) is True
    assert req.predicate(x=-1) is False


def test_post_attaches_ensure_with_return_binding():
    from pyct.contracts import post

    @post("__return__ > 0")
    def f(x):
        return x

    cs = f.__pyct_contracts__
    assert len(cs.ensures) == 1
    ensure = cs.ensures[0]
    assert ensure.condition_args == ()
    assert ensure.description == "__return__ > 0"


def test_post_underscore_normalizes_to_return():
    from pyct.contracts import post

    @post("_ > 0")
    def f(x):
        return x

    ensure = f.__pyct_contracts__.ensures[0]
    co_names = ensure.predicate.__code__.co_names
    assert "__return__" in co_names
    assert "_" not in co_names
    assert ensure.predicate(__return__=5) is True
    assert ensure.predicate(__return__=-1) is False


def test_stacked_preconditions_preserve_source_order():
    from pyct.contracts import pre

    @pre("x > 0")
    @pre("y < 10")
    def f(x, y):
        return x + y

    cs = f.__pyct_contracts__
    assert len(cs.requires) == 2
    assert cs.requires[0].description == "x > 0"
    assert cs.requires[1].description == "y < 10"


def test_mixed_pre_and_post():
    from pyct.contracts import post, pre

    @pre("x > 0")
    @post("__return__ == x * 2")
    def double(x):
        return x * 2

    cs = double.__pyct_contracts__
    assert len(cs.requires) == 1
    assert len(cs.ensures) == 1
    assert cs.requires[0].condition_args == ("x",)
    assert "x" in cs.ensures[0].condition_args


def test_conjunction_predicate_over_multiple_params():
    from pyct.contracts import pre

    @pre("x > 0 and y < 10")
    def f(x, y):
        return x

    req = f.__pyct_contracts__.requires[0]
    assert req.condition_args == ("x", "y")
    assert req.predicate(x=5, y=5) is True
    assert req.predicate(x=5, y=15) is False
    assert req.predicate(x=-1, y=5) is False


def test_disjunction_predicate_over_multiple_params():
    from pyct.contracts import pre

    @pre("x > 0 or y < 10")
    def f(x, y):
        return x

    req = f.__pyct_contracts__.requires[0]
    assert req.condition_args == ("x", "y")
    assert req.predicate(x=5, y=99) is True
    assert req.predicate(x=-1, y=5) is True
    assert req.predicate(x=-1, y=99) is False


def test_negation_predicate():
    from pyct.contracts import pre

    @pre("not (x == 0)")
    def f(x):
        return x

    req = f.__pyct_contracts__.requires[0]
    assert req.condition_args == ("x",)
    assert req.predicate(x=1) is True
    assert req.predicate(x=0) is False


def test_builtin_reference_excluded_from_condition_args():
    from pyct.contracts import pre

    @pre("len(x) > 0")
    def f(x):
        return x

    req = f.__pyct_contracts__.requires[0]
    assert req.condition_args == ("x",)
    assert "len" not in req.condition_args
    assert req.predicate(x=[1]) is True
    assert req.predicate(x=[]) is False


def test_module_global_resolved_from_target_globals():
    from pyct.contracts import pre

    @pre("x > MIN_VAL")
    def f(x):
        return x

    req = f.__pyct_contracts__.requires[0]
    assert req.condition_args == ("x",)
    # MIN_VAL = 0 in this module's globals; predicate eval must
    # resolve it via target.__globals__, not via condition_args binding.
    assert req.predicate(x=5) is True
    assert req.predicate(x=-1) is False


def test_decorator_captures_source_line():
    from pyct.contracts import pre

    @pre("x > 0")  # decorator-call line; captured by inspect.stack
    def f(x):
        return x

    source = f.__pyct_contracts__.requires[0].source
    assert ":" in source
    path, line = source.rsplit(":", 1)
    assert path.endswith("test_contracts_decorators.py")
    assert line.isdigit()


def test_discover_contracts_returns_decorated_set_identity():
    from pyct.contracts import discover_contracts, pre

    @pre("x > 0")
    def f(x):
        return x

    assert discover_contracts(f) is f.__pyct_contracts__


def test_invalid_predicate_syntax_raises_at_decoration():
    from pyct.contracts import PyCTContractSyntaxError, pre

    with pytest.raises(PyCTContractSyntaxError):

        @pre("x >>")
        def f(x):
            return x


def test_non_string_argument_raises_type_error():
    from pyct.contracts import pre

    with pytest.raises(TypeError):

        @pre(123)  # type: ignore[arg-type]
        def f(x):
            return x
