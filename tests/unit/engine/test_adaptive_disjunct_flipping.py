"""Unit tests for adaptive disjunct flipping scheduling on the engine.

The adaptive disjunct flipping subsystem extends the engine with:

* A constraint-picker (``_pick_next_constraint``) that orders the pool
  by chain status — non-chain constraints first, then chain
  constraints whose ``unproductive_streak`` is below
  ``_UNPRODUCTIVE_STREAK_THRESHOLD`` (default 3), then deprioritized
  chain constraints as a last-resort fallback (never fully removed).
* A post-iteration hook (``_post_iteration_update``) that attributes
  the iteration's coverage delta back to the chain whose constraint
  drove the iteration: ``new_lines > 0`` resets ``unproductive_streak``
  and increments ``productive_flips``; ``new_lines == 0`` increments
  ``unproductive_streak``. When the streak first crosses the threshold
  for a chain, ``gen_chain_deprioritized`` ticks once for that chain
  transition (subsequent unproductive flips on the same already-
  deprioritized chain do NOT re-increment).

These tests drive the engine's scheduling internals directly with
hand-built ``Constraint`` instances tagged via the ``chain_id``
attribute. Asserting on the picker/update contract in isolation lets
the test suite verify the rules without booting a full exploration
loop — the end-to-end behaviour is covered by acceptance tests
elsewhere.
"""

from __future__ import annotations

import pytest

from pyct.config.execution import ExecutionConfig
from pyct.engine.engine import Engine
from pyct.engine.state import ExplorationState
from pyct.predicate import Predicate
from pyct.utils.constraint import Constraint


def _tagged_constraint(name: str, chain_id: int | None) -> Constraint:
    """Build a fresh leaf ``Constraint`` carrying ``chain_id`` for the picker.

    The picker reads ``constraint.chain_id`` to decide priority; the
    name fragment goes into the predicate's symbolic expression so each
    constraint is distinguishable in failure output.
    """
    root = Constraint(parent_id=None, predicate=None)
    leaf = root.add_child(Predicate(["=", name, "0"], True))
    leaf.chain_id = chain_id
    return leaf


def _attach_state(engine: Engine, state: ExplorationState) -> None:
    """Wire ``state`` onto ``engine.state`` so picker reads or_chain_stats."""
    engine.state = state


class TestPickerPrefersNonChainConstraintsFirst:
    """``_pick_next_constraint`` returns non-chain constraints before chain ones."""

    def test_non_chain_constraint_returned_before_chain_constraint(self):
        engine = Engine(ExecutionConfig())
        state = ExplorationState()
        _attach_state(engine, state)

        chain_first = _tagged_constraint("chain_a_VAR", chain_id=1)
        non_chain = _tagged_constraint("free_VAR", chain_id=None)
        engine.constraints_to_solve = [chain_first, non_chain]

        picked = engine._pick_next_constraint()

        assert picked is non_chain, (
            "expected the non-chain constraint to be returned first "
            "even when it was queued behind a chain-tagged constraint; "
            f"got {picked!r}"
        )


class TestProductiveFlipResetsStreak:
    """Coverage-gaining iteration on a chain resets that chain's streak."""

    def test_new_lines_resets_unproductive_streak_and_bumps_productive(self):
        from pyct.engine.state import ChainStats

        engine = Engine(ExecutionConfig())
        state = ExplorationState()
        state.or_chain_stats[5] = ChainStats(
            attempted_flips=4,
            productive_flips=1,
            unproductive_streak=2,
        )
        _attach_state(engine, state)

        engine._post_iteration_update(chain_id=5, new_lines_covered=3)

        stats = state.or_chain_stats[5]
        assert stats.unproductive_streak == 0, (
            "productive flip must reset unproductive_streak to 0; "
            f"got {stats.unproductive_streak}"
        )
        assert stats.productive_flips == 2, (
            "productive flip must increment productive_flips by 1; "
            f"got {stats.productive_flips}"
        )


class TestUnproductiveStreakDeprioritizes:
    """After 3 unproductive flips, the chain is skipped in favor of other work."""

    def test_chain_at_threshold_is_skipped_when_other_work_exists(self):
        from pyct.engine.state import ChainStats

        engine = Engine(ExecutionConfig())
        state = ExplorationState()
        # Chain has hit the deprioritization threshold (3).
        state.or_chain_stats[9] = ChainStats(
            attempted_flips=3,
            productive_flips=0,
            unproductive_streak=3,
        )
        _attach_state(engine, state)

        deprioritized = _tagged_constraint("chain_9_VAR", chain_id=9)
        other_chain = _tagged_constraint("chain_other_VAR", chain_id=11)
        engine.constraints_to_solve = [deprioritized, other_chain]

        picked = engine._pick_next_constraint()

        assert picked is other_chain, (
            "expected a non-deprioritized chain constraint to be picked "
            "before the deprioritized one when both are in the pool; "
            f"got {picked!r}"
        )


class TestDeprioritizedChainStaysInPoolAsLastResort:
    """Deprioritized chain constraints are not removed — only deferred."""

    def test_deprioritized_chain_returned_when_no_other_work_exists(self):
        from pyct.engine.state import ChainStats

        engine = Engine(ExecutionConfig())
        state = ExplorationState()
        state.or_chain_stats[2] = ChainStats(
            attempted_flips=4,
            productive_flips=0,
            unproductive_streak=4,
        )
        _attach_state(engine, state)

        deprioritized = _tagged_constraint("chain_2_VAR", chain_id=2)
        engine.constraints_to_solve = [deprioritized]

        picked = engine._pick_next_constraint()

        assert picked is deprioritized, (
            "expected the deprioritized chain constraint to be returned "
            "as last-resort fallback when no higher-priority work exists; "
            f"got {picked!r}"
        )


class TestChainDeprioritizedCounterFires:
    """``gen_chain_deprioritized`` increments exactly once per chain transition."""

    def test_streak_crossing_threshold_bumps_counter_once(self):
        from pyct.engine.state import ChainStats

        engine = Engine(ExecutionConfig())
        state = ExplorationState()
        # Chain at streak=2 — one more unproductive flip crosses the
        # default threshold of 3.
        state.or_chain_stats[8] = ChainStats(
            attempted_flips=2,
            productive_flips=0,
            unproductive_streak=2,
        )
        _attach_state(engine, state)

        engine._post_iteration_update(chain_id=8, new_lines_covered=0)

        assert state.or_chain_stats[8].unproductive_streak == 3
        assert state.gen_chain_deprioritized == 1, (
            "expected gen_chain_deprioritized to tick once on the chain "
            "transition into the deprioritized state; got "
            f"{state.gen_chain_deprioritized}"
        )

    def test_repeated_unproductive_flips_on_deprioritized_chain_do_not_re_increment(self):
        from pyct.engine.state import ChainStats

        engine = Engine(ExecutionConfig())
        state = ExplorationState()
        # Chain already past threshold.
        state.or_chain_stats[8] = ChainStats(
            attempted_flips=5,
            productive_flips=0,
            unproductive_streak=5,
        )
        state.gen_chain_deprioritized = 1  # the transition already fired
        _attach_state(engine, state)

        engine._post_iteration_update(chain_id=8, new_lines_covered=0)
        engine._post_iteration_update(chain_id=8, new_lines_covered=0)

        assert state.gen_chain_deprioritized == 1, (
            "expected gen_chain_deprioritized to stay at 1 — additional "
            "unproductive flips on an already-deprioritized chain must "
            f"not re-increment; got {state.gen_chain_deprioritized}"
        )


if __name__ == "__main__":  # pragma: no cover — keep ``python <file>`` quick
    pytest.main([__file__, "-v"])
