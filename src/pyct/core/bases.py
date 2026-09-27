"""Each tracked class and the base type Python's own value has: the one table of them.

A tracked value reports its base type as its class, and its class called
outside pyct's construction builds that type's value (`pyct.core.values`).
Each tracked type adds its row here.
"""

from pyct.core import values
from pyct.core.bools import ConcolicBool
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.lists import ConcolicList
from pyct.core.strs import ConcolicStr

# the table: each tracked class, and the base type it reports
_ROWS: dict[type, type] = {
    ConcolicInt: int,
    ConcolicFloat: float,
    ConcolicStr: str,
    ConcolicBool: bool,
    ConcolicList: list,
}
values.BASES.update(_ROWS)
values.BASES_BY_ID.update({id(tracked): base for tracked, base in _ROWS.items()})
