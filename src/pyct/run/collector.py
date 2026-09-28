"""The cyclic garbage collector held off while pyct's process handles one input's facts.

An input's facts are many small lists, tuples and forks, and printing its
line and adding its path to the tree make as many again; none of them is
garbage, and none holds a cycle. The collector still walks them all each
time enough have been made, so with the countdown's 110,000 forks it took
about a third of the time pyct spent on the input after its deadline.
Only pyct's own code runs while it is held off, and the ``tell`` callbacks
a ``run()`` caller hands in, which take each finished input: never the
target's.
"""

import contextlib
import gc
from collections.abc import Generator


@contextlib.contextmanager
def collector_paused() -> Generator[None]:
    """Hold off the cyclic collector for the block, then leave it as the block found it.

    A cycle made meanwhile is collected once the collector runs again. A
    caller that had turned the collector off finds it still off.
    """
    was_on = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if was_on:
            gc.enable()
