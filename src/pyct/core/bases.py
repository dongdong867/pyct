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

values.BASES.update(
    {
        ConcolicInt: int,
        ConcolicFloat: float,
        ConcolicStr: str,
        ConcolicBool: bool,
        ConcolicList: list,
    }
)
