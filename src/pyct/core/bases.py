"""Each tracked class and the base type Python's own value has: the one table of them.

A tracked value reports its base type as its class, its class carries that
type's names, which Python writes into its messages, and its class called
outside pyct's construction builds that type's value (`pyct.core.values`).
Each tracked type adds its row here.
"""

from pyct.core import values
from pyct.core.bools import ConcolicBool
from pyct.core.dict_views import ConcolicItems, ConcolicKeys, ConcolicValues
from pyct.core.dicts import ConcolicDict
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.lists import ConcolicList
from pyct.core.ranges import ConcolicRange
from pyct.core.strs import ConcolicStr

# the table: each tracked class, and the base type it reports
_ROWS: dict[type, type] = {
    ConcolicInt: int,
    ConcolicFloat: float,
    ConcolicStr: str,
    ConcolicBool: bool,
    ConcolicList: list,
    ConcolicDict: dict,
    ConcolicRange: range,
}
# each tracked class, which a router asks of a plain value's items before it hands them to Python
TRACKED_CLASSES = frozenset(_ROWS)
values.BASES.update(_ROWS)
values.BASES_BY_ID.update({id(tracked): base for tracked, base in _ROWS.items()})
for tracked, base in _ROWS.items():
    values.named_as(tracked, base)

# a dict's views, which the `type` router reads as Python's view types by their identity alone.
# They have no row: a row also builds its base type's plain value and routes a join's items,
# and a view has no plain value of its own (read-a-dict-view-s-type-as-python-s)
_VIEWS = (ConcolicKeys, ConcolicValues, ConcolicItems)
values.BASES_BY_ID.update({id(view): type(view.python({})) for view in _VIEWS})
