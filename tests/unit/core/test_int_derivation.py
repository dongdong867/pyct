import sys

import pytest

from pyct.core import ints, numbers, values
from pyct.core.ints import ConcolicInt
from tests.unit.core.own_scan import without_the_helper, written_in

# the operations ConcolicInt leaves to int, written out because the derivation reads the same
# sets the production code does: a name that slipped out of the taught set would run as int's
# own with no downgrade, silently. Nineteen on the floor version; a newer Python may add another
UNTAUGHT_OPERATIONS = (
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
    "bit_count",
    "bit_length",
    "to_bytes",
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
    reason="the nineteen are counted on the floor; a newer Python may define another int method",
)
def test_a_concolic_int_downgrades_the_nineteen_operations_it_has_not_taught() -> None:
    assert _derived_downgrades() == set(UNTAUGHT_OPERATIONS)


def test_the_derivation_wraps_every_untaught_operation_and_nothing_kept() -> None:
    derived = _derived_downgrades()

    # the version gate above is on the count, not on the list; these nineteen exist on every
    # Python pyct runs on, so each one is a downgrade there too
    assert set(UNTAUGHT_OPERATIONS) <= derived
    # a wrapped kept name would cost a dict key a downgrade, and a wrapped `__getattribute__`
    # recurses on the first attribute read; the stand-in tests show the class body is skipped
    assert derived.isdisjoint(numbers.INT_KEPT)


def test_every_operation_that_reaches_ints_own_goes_through_the_helper() -> None:
    # a call into int written without the helper leaves its raise blamed on pyct, silently.
    # ConcolicInt's dunders are written in three files: its own, numbers for the operations it
    # shares with a bool and values for the downgrade closures, so the scan covers all three.
    # An operation hands the call to a closure it holds, so what a function holds counts
    files = {ints.__file__, numbers.__file__, values.__file__}

    # the scan read the compares, the arithmetic and a derived downgrade, so an empty answer
    # is not an empty scan
    assert {"__lt__", "__add__", "__divmod__", "__pow__", "__bool__", "__and__"} <= (
        written_in(ConcolicInt, files).keys()
    )
    # these hand the value itself back and never call int, so they have nothing to guard
    rounding = {"__trunc__", "__floor__", "__ceil__"}
    assert (
        without_the_helper(ConcolicInt, files)
        == {
            "__pos__",
            "__index__",
            "__copy__",
            "__deepcopy__",
        }
        | rounding
    )
