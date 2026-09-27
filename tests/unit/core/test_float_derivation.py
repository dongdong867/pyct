import copy
import math
import sys

import pytest

from pyct.core import floats, numbers, values
from pyct.core.branch import Downgrade, SinkItem
from pyct.core.floats import ConcolicFloat
from tests.unit.core.own_scan import without_the_helper, written_in

# the operations ConcolicFloat leaves to float, written out because the derivation reads the
# same sets the production code does: a name that slipped out of the taught set would run as
# float's own with no downgrade, silently. Eight on the floor version, `__str__` among them
# because float inherits it; a newer Python may add another. `round(x, n)` is a downgrade too,
# named `__round__`, but by `__round__`'s own hand, since `round(x)` is taught
UNTAUGHT_OPERATIONS = (
    "__pow__",
    "__rpow__",
    "__int__",
    "__float__",
    "__str__",
    "__format__",
    "as_integer_ratio",
    "hex",
)


def _derived_downgrades() -> set[str]:
    """The names the derivation wrapped: what `downgraded` built, and nothing else on the class."""
    return {
        name
        for name, member in vars(ConcolicFloat).items()
        if getattr(member, "__qualname__", "").startswith("downgraded.")
    }


@pytest.mark.skipif(
    sys.version_info[:2] != (3, 12),
    reason="the eight are counted on the floor; a newer Python may define another method",
)
def test_a_concolic_float_downgrades_the_eight_operations_it_has_not_taught() -> None:
    assert _derived_downgrades() == set(UNTAUGHT_OPERATIONS)


def test_the_derivation_wraps_every_untaught_operation_and_nothing_kept() -> None:
    derived = _derived_downgrades()

    assert set(UNTAUGHT_OPERATIONS) <= derived
    # a wrapped kept name would cost a dict key a downgrade, and a wrapped `__getattribute__`
    # recurses on the first attribute read
    assert derived.isdisjoint(floats._KEPT)


def test_text_conversion_is_a_downgrade_though_float_inherits_it() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(2.5, expression="x", sink=sink)

    assert str(x) == "2.5"
    assert sink == [Downgrade(name="__str__")]


def test_the_object_plumbing_records_nothing() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(2.5, expression="x", sink=sink)

    assert repr(x) == "2.5"
    assert hash(x) == hash(2.5)
    # the same key is found by identity; an equal one would test `==` for truth, a fork
    assert {x: "found"}[x] == "found"
    assert sink == []


def test_a_copy_is_the_value_itself() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(2.5, expression="x", sink=sink)

    assert copy.copy(x) is x
    assert copy.deepcopy(x) is x
    assert sink == []


def test_a_downgrade_that_raises_is_the_targets_and_records_nothing() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(math.nan, expression="x", sink=sink)

    with pytest.raises(ValueError) as raised:
        int(x)

    assert values.raised_by_target(raised.value)
    assert sink == []


def test_every_operation_that_reaches_floats_own_goes_through_the_helper() -> None:
    # a call into float written without the helper leaves its raise blamed on pyct, silently.
    # ConcolicFloat's dunders are written in three files: its own, numbers for the compare and
    # unary closures it shares with the other numbers, and values for the downgrade closures,
    # so the scan covers all three. An operation hands the call to a closure it holds, so what
    # a function holds counts
    files = {floats.__file__, numbers.__file__, values.__file__}

    # the scan read the compares, the arithmetic, the unary operations and a derived downgrade,
    # so an empty answer is not an empty scan
    assert {"__lt__", "__add__", "__neg__", "__pow__", "__bool__", "is_integer"} <= (
        written_in(ConcolicFloat, files).keys()
    )
    # these hand the value itself back and never call float, so they have nothing to guard
    assert without_the_helper(ConcolicFloat, files) == {"__pos__", "__copy__", "__deepcopy__"}
