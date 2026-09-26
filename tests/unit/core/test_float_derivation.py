import copy
import math
import sys

import pytest

from pyct.core import bools, floats, values
from pyct.core.branch import Downgrade, SinkItem
from pyct.core.floats import ConcolicFloat

# the operations ConcolicFloat leaves to float, written out because the derivation reads the
# same sets the production code does: a name that slipped out of the taught set would run as
# float's own with no downgrade, silently. Nineteen on the floor version, `__str__` among them
# because float inherits it; a newer Python may add another
UNTAUGHT_OPERATIONS = (
    "__floordiv__",
    "__rfloordiv__",
    "__mod__",
    "__rmod__",
    "__divmod__",
    "__rdivmod__",
    "__pow__",
    "__rpow__",
    "__floor__",
    "__ceil__",
    "__trunc__",
    "__round__",
    "__int__",
    "__float__",
    "__str__",
    "__format__",
    "as_integer_ratio",
    "conjugate",
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
    reason="the nineteen are counted on the floor; a newer Python may define another method",
)
def test_a_concolic_float_downgrades_the_nineteen_operations_it_has_not_taught() -> None:
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
    # ConcolicFloat's dunders are written in three files: its own, bools for the compare
    # closures and values for the downgrade closures, so the scan covers all three
    written_here = {
        name: code
        for name, member in vars(ConcolicFloat).items()
        if (code := getattr(member, "__code__", None)) is not None
        and code.co_filename in {floats.__file__, bools.__file__, values.__file__}
    }
    # a closure that hands the call to bools' compare or to a downgrade closure reaches float
    # through the helper as well, since each of those calls it
    reaches_float = {"own", "followed", "downgrade"}
    without_the_helper = {
        name
        for name, code in written_here.items()
        if not reaches_float & (set(code.co_names) | set(code.co_freevars))
    }

    # these hand the value itself back and never call float, so they have nothing to guard
    assert without_the_helper == {"__pos__", "__copy__", "__deepcopy__"}
