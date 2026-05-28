"""Unit tests for substring emission let-binding optimisation.

These tests assert the post-green SMT shape produced by
``core/str/helpers.py:_build_substr_expression``. The current emission
duplicates the start expression once in the substr position and again
inside the ``(- end start)`` length term — the optimisation wraps the
output in an SMT ``let`` so each bound is named once and referenced by
name (``(let ((__a start) (__b end)) (str.substr s __a (- __b __a)))``).
When ``start`` is a concrete int, the optimisation skips the binding
for that arg and inlines the literal int directly inside the let body.

Every emission additionally bumps an ``ExplorationState`` counter
(``gen_substr_let_bound``) so downstream telemetry can attribute
formula-shrink wins to this rewrite.

The fixtures here assert on the symbolic ``.expr`` tree, not on
behaviour (concrete result), because the optimisation is structural —
behaviour is already locked in ``test_str_operations.py::test_slice``.
"""

from __future__ import annotations

from pyct.core.int import ConcolicInt
from pyct.core.str.helpers import SubstringHelper
from pyct.core.str.str import ConcolicStr
from pyct.engine.state import ExplorationState


class TestSubstrLetBinding:
    """Structural assertions on the substr SMT expression tree."""

    def test_symbolic_start_and_end_emit_let_form(self, engine):
        """`s[i:j]` with symbolic start and end emits a ``let`` binding."""
        s = ConcolicStr("hello", "s", engine)
        i = ConcolicInt(1, ["i"], engine)
        j = ConcolicInt(4, ["j"], engine)

        result = SubstringHelper.substr(s, i, j)

        # Post-green shape:
        #   (let ((__a i) (__b j)) (str.substr s __a (- __b __a)))
        # Current shape:
        #   (str.substr s i (- j i))
        # so expr[0] is "str.substr", not "let".
        assert result.expr[0] == "let", (
            f"expected let-bound substr emission, got root {result.expr[0]!r}; "
            "start expression is duplicated in the length term without let-binding."
        )

    def test_concrete_start_skips_binding_and_inlines_literal(self, engine):
        """`s[5:n]` with concrete start inlines the literal int in the let body."""
        s = ConcolicStr("helloworld", "s", engine)
        n = ConcolicInt(7, ["n"], engine)

        result = SubstringHelper.substr(s, 5, n)

        # Post-green shape:
        #   (let ((__b n)) (str.substr s 5 (- __b 5)))
        # Bindings list should contain a single binding (only `n`) — the
        # concrete `5` is NOT bound; it appears as a bare int literal at
        # both occurrences inside the let body.
        assert result.expr[0] == "let", (
            f"expected let-bound substr emission, got root {result.expr[0]!r}; "
            "concrete start `5` is emitted without the let-wrapper fast-path."
        )
        bindings = result.expr[1]
        assert len(bindings) == 1, (
            f"expected single binding for symbolic end only, got {len(bindings)} "
            f"bindings: {bindings!r}. Concrete `5` should be inlined, not bound."
        )

    def test_emission_increments_substr_let_bound_counter(self, engine):
        """`_build_substr_expression` bumps ``state.gen_substr_let_bound``."""
        state = ExplorationState()
        engine.state = state

        s = ConcolicStr("hello", "s", engine)
        i = ConcolicInt(1, ["i"], engine)
        j = ConcolicInt(4, ["j"], engine)

        SubstringHelper.substr(s, i, j)

        assert state.gen_substr_let_bound == 1, (
            "expected gen_substr_let_bound to bump to 1 after one substr emission; "
            f"got {getattr(state, 'gen_substr_let_bound', 'ATTRIBUTE-MISSING')!r}."
        )
