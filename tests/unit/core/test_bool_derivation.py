import sys

import pytest

from pyct.core import bools, numbers, values
from pyct.core.bools import ConcolicBool
from pyct.core.ints import ConcolicInt
from tests.unit.core.own_scan import without_the_helper, written_in

# the operations ConcolicBool leaves to int, written out because the derivation reads the same
# sets the production code does: a name that slipped out of the taught set would run as int's
# own with no downgrade, silently. Fifteen on the floor version; a newer Python may add another
UNTAUGHT_OPERATIONS = (
    "__truediv__",
    "__rtruediv__",
    "__rpow__",
    "__lshift__",
    "__rlshift__",
    "__rshift__",
    "__rrshift__",
    "__rand__",
    "__ror__",
    "__rxor__",
    "__invert__",
    "__int__",
    "__float__",
    "__str__",
    "__format__",
)

# what a bool teaches that an int leaves to int: `&`, `|` and `^` between two bools
BOOLS_OWN = {"__and__", "__or__", "__xor__"}


def _downgrades(cls: type) -> set[str]:
    """The names a type records as downgrades: what `downgraded` built, and nothing else."""
    return {
        name
        for name, member in vars(cls).items()
        if getattr(member, "__qualname__", "").startswith("downgraded.")
    }


@pytest.mark.skipif(
    sys.version_info[:2] != (3, 12),
    reason="the fifteen are counted on the floor; a newer Python may define another int method",
)
def test_a_concolic_bool_downgrades_the_fifteen_operations_it_has_not_taught() -> None:
    assert _downgrades(ConcolicBool) == set(UNTAUGHT_OPERATIONS)


def test_the_derivation_wraps_every_untaught_operation_and_nothing_kept() -> None:
    derived = _downgrades(ConcolicBool)

    assert set(UNTAUGHT_OPERATIONS) <= derived
    assert derived.isdisjoint(numbers.INT_KEPT + numbers.INT_NOT_YET)


def test_a_bool_loses_what_an_int_loses_but_what_it_teaches_itself() -> None:
    # a bool is the int 1 or 0, so what an int cannot follow a bool cannot either, on any Python
    assert _downgrades(ConcolicInt) - BOOLS_OWN <= _downgrades(ConcolicBool)


def test_every_operation_that_reaches_ints_own_goes_through_the_helper() -> None:
    # a call into int written without the helper leaves its raise blamed on pyct, silently.
    # ConcolicBool's dunders are written in three files: its own, numbers for the operations it
    # shares with an int and values for the downgrade closures, so the scan covers all three
    files = {bools.__file__, numbers.__file__, values.__file__}

    assert {"__lt__", "__add__", "__and__", "__round__", "__format__", "__invert__"} <= (
        written_in(ConcolicBool, files).keys()
    )
    # a copy hands the value itself back, and `__repr__` reads the bool's own truth, which
    # cannot raise
    assert without_the_helper(ConcolicBool, files) == {"__copy__", "__deepcopy__", "__repr__"}
