import sys

import pytest

from pyct.core import bools, values
from pyct.core.bools import ConcolicBool
from pyct.core.ints import ConcolicInt
from tests.unit.core.test_strs import _reaches_through_the_helper

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
    assert derived.isdisjoint(bools.INT_KEPT + bools.INT_NOT_YET)


def test_a_bool_loses_what_an_int_loses_but_what_it_teaches_itself() -> None:
    # a bool is the int 1 or 0, so what an int cannot follow a bool cannot either, on any Python
    assert _downgrades(ConcolicInt) - BOOLS_OWN <= _downgrades(ConcolicBool)


def test_every_operation_that_reaches_ints_own_goes_through_the_helper() -> None:
    # a call into int written without the helper leaves its raise blamed on pyct, silently.
    # ConcolicBool's dunders are written in its own file and in values, for the downgrade closures
    written_here = {
        name: member
        for name, member in vars(ConcolicBool).items()
        if (code := getattr(member, "__code__", None)) is not None
        and code.co_filename in {bools.__file__, values.__file__}
    }
    # an operation a bool runs as ConcolicInt's own reaches int where the int scan reads it
    delegated = {
        name
        for name, member in written_here.items()
        if member.__qualname__.startswith("_as_an_int.")
    }

    assert delegated <= vars(ConcolicInt).keys() - _downgrades(ConcolicInt)
    without_the_helper = {
        name
        for name, member in written_here.items()
        if name not in delegated and not _reaches_through_the_helper(member)
    }
    # a copy hands the value itself back, `__repr__` reads the bool's own truth, which cannot
    # raise, and `__round__` rounds the int the bool is, through ConcolicInt's own
    assert without_the_helper == {"__copy__", "__deepcopy__", "__repr__", "__round__"}
