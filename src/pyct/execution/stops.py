"""pyct's process-wide stop, and what counts as a person's stop where a call runs.

``Stopped`` lives here, below ``run``, which raises it for a SIGTERM (see
``pyct.run.process``), so that the deadline can tell a stop on its way out
from a raise of the target's own and hold its alarm back for it.
"""

from __future__ import annotations


class Stopped(BaseException):
    """pyct's process was told to stop, by a SIGTERM (see ``pyct.run.launch``).

    A BaseException, as a Ctrl-C's KeyboardInterrupt is, so pyct's code lets
    it through and ends each process pyct started on the way out. Target
    code that catches BaseException can catch it and go on, so a stop also
    refuses every input after it (see ``pyct.run.process.refuse_after_a_stop``).
    """


# what a person's stop raises: a Ctrl-C, and a SIGTERM in pyct's process
STOPS = (KeyboardInterrupt, Stopped)
