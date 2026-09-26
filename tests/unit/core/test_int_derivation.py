import sys

import pytest

from pyct.core import bools, ints, values
from pyct.core.ints import ConcolicInt

# the operations ConcolicInt leaves to int, written out because the derivation reads the same
# sets the production code does: a name that slipped out of the taught set would run as int's
# own with no downgrade, silently. Eighteen on the floor version; a newer Python may add another
UNTAUGHT_OPERATIONS = (
    "__truediv__",
    "__rtruediv__",
    "__rpow__",
    "__lshift__",
    "__rlshift__",
    "__rshift__",
    "__rrshift__",
    "__and__",
    "__rand__",
    "__or__",
    "__ror__",
    "__xor__",
    "__rxor__",
    "__invert__",
    "__int__",
    "__float__",
    "__str__",
    "__format__",
)


# the names the derivation wrapped: what `downgraded` built, and nothing else on the class
def _derived_downgrades() -> set[str]:
    return {
        name
        for name, member in vars(ConcolicInt).items()
        if getattr(member, "__qualname__", "").startswith("downgraded.")
    }


@pytest.mark.skipif(
    sys.version_info[:2] != (3, 12),
    reason="the eighteen are counted on the floor; a newer Python may define another int method",
)
def test_a_concolic_int_downgrades_the_eighteen_operations_it_has_not_taught() -> None:
    assert _derived_downgrades() == set(UNTAUGHT_OPERATIONS)


def test_the_derivation_wraps_every_untaught_operation_and_nothing_kept() -> None:
    derived = _derived_downgrades()

    # the version gate above is on the count, not on the list; these eighteen exist on every
    # Python pyct runs on, so each one is a downgrade there too
    assert set(UNTAUGHT_OPERATIONS) <= derived
    # a wrapped kept name would cost a dict key a downgrade, and a wrapped `__getattribute__`
    # recurses on the first attribute read; the stand-in tests show the class body is skipped
    assert derived.isdisjoint(ints._KEPT + ints._NOT_YET)


def test_every_operation_that_reaches_ints_own_goes_through_the_helper() -> None:
    # a call into int written without the helper leaves its raise blamed on pyct, silently.
    # ConcolicInt's dunders are written in three files: its own, bools for the compare closures
    # and values for the downgrade closures, so the scan covers all three
    written_here = {
        name: code
        for name, member in vars(ConcolicInt).items()
        if name.startswith("__")
        and (code := getattr(member, "__code__", None)) is not None
        and code.co_filename in {ints.__file__, bools.__file__, values.__file__}
    }
    # a downgrade closure reaches int through the helper itself, so handing it the call counts;
    # what makes one is being built by downgraded, not what it is called
    reaches_int = {"own"} | {
        name
        for name, value in vars(ints).items()
        if getattr(value, "__qualname__", "").startswith("downgraded.")
    }
    without_the_helper = {
        name for name, code in written_here.items() if not reaches_int & set(code.co_names)
    }

    # these hand the value itself back and never call int, so they have nothing to guard
    rounding = {"__trunc__", "__floor__", "__ceil__"}
    assert without_the_helper == {"__pos__", "__index__", "__copy__", "__deepcopy__"} | rounding
