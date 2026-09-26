"""The mark for a test whose deadline fires in the test process: it runs with coverage paused.

coverage.py's tracer calls back into Python to lock its data. The deadline raises from a
SIGALRM handler, and Python can run that handler inside the callback, after the lock is taken
or before it is released. The lock then stays held, and the next traced call waits on it
forever. With coverage paused for the test, the tracer takes no lock. ``run_pyct`` in the
acceptance harness keeps coverage out of a pyct subprocess with a budget for the same reason.
So no measured run reaches the lines only a fired alarm runs; each carries
``# pragma: no cover``, and these tests check them.
"""

import pytest

DEADLINE_FIRES = pytest.mark.no_cover
